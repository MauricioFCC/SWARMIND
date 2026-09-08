"""competence_model.py — Beta posterior por (agente, skill) + Thompson (ADR-0075).

WHAT: Modela la competencia de cada par (agente, skill) con una posterior
Beta(alpha, beta) actualizada por execution traces; seleccion con Thompson
sampling o utilidad max(competencia - lambda*costo); expone imp@k.
WHY: Frontera (SkillOrchestra, Wang 2026) — evita routing collapse
(uno-solo-gana-todo) manteniendo exploracion; imp@k (HyperAgents,
arXiv:2603.19461) mide la mejora transferente por experimento.
WHERE: ``agent_selector`` / orquestador: elegir agente por skill con
evidencia acumulada en lugar de keywords fijas.

Uso:
    model = CompetenceModel(agents=("builder", "guardian"), skills=("tdd",))
    agente = model.select(skill="tdd")
    model.update(agente, "tdd", success=True)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

logger = logging.getLogger("harness.orchestrator.competence_model")

#: Prior alpha/beta (Beta(1,1) = uniforme; neutro).
PRIOR_ALPHA = 1.0
PRIOR_BETA = 1.0
#: Snapshot cada N updates para imp@k.
DEFAULT_SNAPSHOT_EVERY = 10


@dataclass(frozen=True)
class BetaPosterior:
    """Posterior Beta de un par (agente, skill).

    Attributes:
        successes: Exitos observados (+ prior).
        failures: Fallos observados (+ prior).
        mean: Media de la posterior (successes / total).
    """

    successes: float
    failures: float

    @property
    def mean(self) -> float:
        """Media de la Beta (exitos / total)."""
        total = self.successes + self.failures
        return self.successes / total if total > 0 else 0.0


class CompetenceModel:
    """Competencia (agente x skill) con Beta posteriors y Thompson sampling.

    Args:
        agents: Agentes conocidos.
        skills: Skills conocidas.
        snapshot_every: Cada cuantos updates se toma snapshot para imp@k.
        rng: Generador aleatorio inyectable (tests deterministas).
    """

    def __init__(
        self,
        agents: tuple[str, ...],
        skills: tuple[str, ...],
        snapshot_every: int = DEFAULT_SNAPSHOT_EVERY,
        rng: random.Random | None = None,
    ) -> None:
        """Inicializa el modelo con priors uniformes por par."""
        self._agents = tuple(agents)
        self._skills = tuple(skills)
        self._snapshot_every = snapshot_every
        self._rng = rng or random.Random()
        self._posterior: dict[tuple[str, str], list[float]] = {}
        for agent in self._agents:
            for skill in self._skills:
                self._posterior[(agent, skill)] = [PRIOR_ALPHA, PRIOR_BETA]
        self._updates_since_snapshot = 0
        self._snapshots: list[float] = []

    def _require_pair(self, agent: str, skill: str) -> list[float]:
        """Valida el par y retorna su estado Beta mutable.

        Args:
            agent: Agente.
            skill: Skill.

        Returns:
            Lista [alpha, beta] del par.

        Raises:
            ValueError: Si el par es desconocido (WHAT+WHY+WHERE).
        """
        state = self._posterior.get((agent, skill))
        if state is None:
            raise ValueError(
                f"WHAT: par desconocido ({agent!r}, {skill!r}). "
                f"WHY: el modelo solo conoce agentes={list(self._agents)} "
                f"skills={list(self._skills)}. "
                "WHERE: CompetenceModel._require_pair"
            )
        return state

    def update(self, agent: str, skill: str, success: bool) -> None:
        """Actualiza la posterior con un execution trace.

        Args:
            agent: Agente que ejecuto.
            skill: Skill ejecutada.
            success: True si la ejecucion fue exitosa.

        Raises:
            ValueError: Si el par es desconocido.
        """
        state = self._require_pair(agent, skill)
        state[0 if success else 1] += 1
        self._updates_since_snapshot += 1
        if self._updates_since_snapshot >= self._snapshot_every:
            self._updates_since_snapshot = 0
            mean = self._posterior[(agent, skill)][0] / sum(self._posterior[(agent, skill)])
            self._snapshots.append(mean)
            logger.debug("competence_model: snapshot %.3f", mean)

    def posterior(self, agent: str, skill: str) -> BetaPosterior:
        """Posterior actual del par (agente, skill).

        Args:
            agent: Agente.
            skill: Skill.

        Returns:
            BetaPosterior frozen.

        Raises:
            ValueError: Si el par es desconocido.
        """
        state = self._require_pair(agent, skill)
        return BetaPosterior(successes=state[0], failures=state[1])

    def select(
        self,
        skill: str,
        cost_weight: float = 0.0,
        costs: dict[str, float] | None = None,
    ) -> str:
        """Selecciona agente con Thompson sampling (o utilidad costo-ajustada).

        Args:
            skill: Skill a ejecutar.
            cost_weight: Lambda de penalizacion de costo (0 = solo competencia).
            costs: Costo por agente (ej. tokens estimados o USD).

        Returns:
            Agente seleccionado.

        Raises:
            ValueError: Si la skill es desconocida.
        """
        if skill not in self._skills:
            raise ValueError(
                f"WHAT: skill desconocida: {skill!r}. "
                f"WHY: el modelo solo conoce {list(self._skills)}. "
                "WHERE: CompetenceModel.select"
            )
        costs = costs or {}
        best_agent = self._agents[0]
        best_score = -1.0e18
        for agent in self._agents:
            state = self._posterior[(agent, skill)]
            sample = self._rng.betavariate(state[0], state[1])
            penalty = cost_weight * costs.get(agent, 0.0)
            score = sample - penalty
            if score > best_score:
                best_score = score
                best_agent = agent
        return best_agent

    def imp_at_k(self, metric_fn, k: int) -> float:
        """Mejora transferente por experimento (HyperAgents imp@k).

        Args:
            metric_fn: Callable(model) -> metrica a comparar entre snapshots.
            k: Numero de experimentos entre el primer y el ultimo snapshot.

        Returns:
            (metrica_ultima - metrica_primera_snapshot) / max(k, 1); 0.0 si
            hay menos de 2 snapshots.

        Raises:
            ValueError: Si k < 1 (WHAT+WHY+WHERE).
        """
        if k < 1:
            raise ValueError(
                f"WHAT: k invalido: {k}. "
                "WHY: imp@k divide por experimentos; k debe ser >= 1. "
                "WHERE: CompetenceModel.imp_at_k"
            )
        if len(self._snapshots) < 2:
            return 0.0
        first = metric_fn(self)
        # La metrica externa mira el estado actual; el snapshot inicial se
        # interpola con la primera diferencia registrada (posterior mean).
        return (first - self._snapshots[0]) / max(k, 1)
