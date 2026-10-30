"""Loop de mineria de alpha (spec frontera 11.16 — NVIDIA + AlphaMCTS + QuantaAlpha).

WHAT: orquestador cerrado que integra los 5 sistemas frontera sobre los
primitivos deterministas del paquete:

- **NVIDIA signal/code/eval** (blog NeMo Agent Toolkit, 2026-05): bucle
  signal(hipotesis) -> code(AST via ``construct_hook``) -> eval(IC/RankIC +
  umbrales) con feedback de sugerencias a la siguiente iteracion y
  ``diversified_init`` (DPI de QuantaAlpha: K hipotesis complementarias).
- **AlphaMCTS** (arXiv 2505.11122): ``search_mcts`` — UCT sobre formulas con
  reward = score del backtest; el seed se evalua en la raiz; expansion =
  ``construct_hook(blueprint=formula)`` con feedback de la razon de rechazo;
  determinista dado hooks + estado (sin azar).
- **QuantaAlpha** (arXiv 2602.07085): trayectorias de mineria con
  ``mutate`` (reescribe SOLO el segmento fallido via reflexion) y
  ``crossover`` (recombina hipotesis del mejor padre con la formula del
  otro); ``evolve_pool`` aplica crossover por pares + mutacion del peor.
- **AlphaAgent/Hubble**: gates ANTES del eval — complejidad (nodos),
  FSA (motif abstracto prohibido) y alineacion hipotesis-factor (score LLM
  inyectado via DI, AlphaAgent mecanismo ii).

Hooks inyectados (DI): ``signal_hook(round, variant) -> hipotesis``;
``construct_hook(ctx, blueprint) -> AST JSON``; ``alignment_hook(hip,
formula) -> float [0,1]``; ``reflect_hook(step) -> payload``. El nucleo es
determinista y sin LLMs: los tests inyectan fakes puros.

WHY: el harness no tenia NINGUNA capacidad alpha (gap IDP); los 5 papers
miden IC 0.03-0.05 con exactamente este mecanismo de puertas + busqueda.

WHERE: ``harness/alpha_mining/mining_loop.py``.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
from numpy.typing import NDArray

from harness.alpha_mining.alpha_zoo import (
    AlphaZoo,
    ZooEntry,
    classify_family,
)
from harness.alpha_mining.factor_dsl import (
    MAX_NODES,
    Expr,
    Field,
    complexity,
    parse_expr,
    to_dict,
    to_formula,
    violates_fsa,
)
from harness.alpha_mining.factor_eval import (
    DEFAULT_MIN_ABS_IC,
    EvalVerdict,
    evaluate_factor,
)

logger = logging.getLogger(__name__)

#: Score minimo de alineacion hipotesis-factor (AlphaAgent mecanismo ii).
ALIGNMENT_MIN = 0.5
#: Motivos de feedback maximos que se arrastran al siguiente contexto.
MAX_FEEDBACK = 6
#: Constante de exploracion UCT por defecto (sqrt(2) de AlphaZero lineage).
DEFAULT_EXPLORATION = 1.41


class Role(str, Enum):
    """Roles del bucle cerrado (NVIDIA signal/code/eval)."""

    SIGNAL = "signal"
    CODE = "code"
    EVAL = "eval"


@dataclass(frozen=True)
class MiningContext:
    """Bundle de prompt dinamico entregado a las hooks (Hubble dynamic prompt).

    Attributes:
        hypothesis: Hipotesis o blueprint de la iteracion.
        round_index: Ronda de mineria.
        forbidden_genes: Genes abstractos prohibidos (FSA anti-crowding).
        feedback: Rechazos accionables de iteraciones previas.
        max_nodes: Limite de complejidad para el generador.
    """

    hypothesis: str
    round_index: int
    forbidden_genes: frozenset[str]
    feedback: tuple[str, ...]
    max_nodes: int = MAX_NODES


@dataclass(frozen=True)
class LoopConfig:
    """Parametros del loop (SSOT del experimento, patron NVIDIA config.yml).

    Attributes:
        seed: Semilla documentada para hooks LLM del caller.
        pool_size: Hipotesis de la inicializacion diversificada.
        exploration: Constante de exploracion UCT.
        min_originality: Similitud maxima vs el zoo.
        max_nodes: Limite de nodos del AST.
        per_family_cap: Cuota por familia en el top-k del zoo.
        ic_threshold: |RankIC| minimo de aceptacion.
        branching: Hermanos maximos por nodo en el arbol MCTS (UCT con
            exploracion real: un nodo con capacidad expande aqui mismo,
            si no desciende por el hijo UCT).
        forbidden_genes: Genes abstractos prohibidos (FSA).
    """

    seed: int = 42
    pool_size: int = 3
    exploration: float = DEFAULT_EXPLORATION
    min_originality: float = 0.8
    max_nodes: int = MAX_NODES
    per_family_cap: int = 2
    ic_threshold: float = DEFAULT_MIN_ABS_IC
    branching: int = 2
    forbidden_genes: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class RoundReport:
    """Resultado de una ronda de mineria.

    Attributes:
        accepted: Entradas que entraron al zoo.
        rejected: Pares (formula, reason) de generaciones rechazadas.
    """

    accepted: tuple[ZooEntry, ...]
    rejected: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class TrajectoryStep:
    """Segmento de una trayectoria de mineria (QuantaAlpha).

    Attributes:
        role: Rol del segmento (signal/code/eval).
        payload: Contenido textual del segmento.
    """

    role: Role
    payload: str


@dataclass(frozen=True)
class Trajectory:
    """Trayectoria end-to-end de mineria (QuantaAlpha: unidad de evolucion).

    Attributes:
        hypothesis: Hipotesis del segmento signal.
        formula: Formula canonica del segmento code (si existe).
        steps: Segmentos en orden.
        reward: Recompensa observable (score del eval).
    """

    hypothesis: str
    formula: str | None
    steps: tuple[TrajectoryStep, ...]
    reward: float


@dataclass(frozen=True)
class MCTSResult:
    """Resultado determinista de ``search_mcts``.

    Attributes:
        best: Formula con mayor score propio observado.
        best_score: Score del mejor nodo.
        visited: Expansiones/evaluaciones realizadas.
        accepted: Formulas que pasaron el eval en la busqueda.
    """

    best: Expr | None
    best_score: float
    visited: int
    accepted: tuple[str, ...]


#: Hook de señal: (round, variante) -> hipotesis textual.
SignalHook = Callable[[int, int], str]
#: Hook de construccion: (ctx, blueprint) -> AST JSON validado por sandbox.
ConstructHook = Callable[[MiningContext, str], Mapping[str, Any]]
#: Hook de reflexión: segmento fallido -> payload reescrito.
ReflectHook = Callable[[TrajectoryStep], str]
#: Hook de alineacion: (hipotesis, formula) -> score [0, 1] (LLM).
AlignmentHook = Callable[[str, str], float]


def mutate(traj: Trajectory, reflect_hook: ReflectHook) -> Trajectory:
    """Mutacion segment-local (QuantaAlpha): reescribe SOLO el paso fallido.

    Args:
        traj: Trayectoria original (intacta: frozen).
        reflect_hook: Reflexion que reescribe el ultimo segmento.

    Returns:
        Trayectoria con el ultimo payload reescrito; el resto es idéntico.
    """
    if not traj.steps:
        return traj
    last = traj.steps[-1]
    rewritten = TrajectoryStep(role=last.role, payload=reflect_hook(last))
    return Trajectory(
        hypothesis=traj.hypothesis,
        formula=traj.formula,
        steps=traj.steps[:-1] + (rewritten,),
        reward=traj.reward,
    )


def crossover(better: Trajectory, worse: Trajectory) -> Trajectory:
    """Crossover de segmentos (QuantaAlpha): hipotesis del mejor + formula del otro.

    Args:
        better: Padre de mayor recompensa (aporta la hipotesis).
        worse: Padre de menor recompensa (aporta la formula).

    Returns:
        Descendiente con segmentos recombinados y reward 0 (sin evaluar).
    """
    steps = better.steps[:-1] + worse.steps[-1:] if better.steps and worse.steps else better.steps
    return Trajectory(
        hypothesis=better.hypothesis,
        formula=worse.formula,
        steps=steps,
        reward=0.0,
    )


class MiningLoop:
    """Loop cerrado de mineria con gates, MCTS y evolucion de trayectorias."""

    def __init__(
        self,
        panel: dict[Field, NDArray[np.float64]],
        zoo: AlphaZoo,
        config: LoopConfig,
        *,
        signal_hook: SignalHook,
        construct_hook: ConstructHook,
        alignment_hook: AlignmentHook | None = None,
    ) -> None:
        """Cablea panel, zoo, config y hooks (DI: sin LLMs en el nucleo).

        Args:
            panel: Panel OHLCV determinista.
            zoo: Zoo durable donde depositar factores aceptados.
            config: Parametros del loop.
            signal_hook: Generador de hipotesis.
            construct_hook: Generador de AST JSON.
            alignment_hook: scoring LLM de alineacion (opcional).
        """
        self.panel = panel
        self.zoo = zoo
        self._config = config
        self._signal = signal_hook
        self._construct = construct_hook
        self._align = alignment_hook
        self._feedback: list[str] = []

    def diversified_init(self, round_index: int) -> tuple[str, ...]:
        """Inicializacion diversificada de hipotesis (QuantaAlpha DPI).

        Args:
            round_index: Ronda de mineria.

        Returns:
            ``pool_size`` hipotesis de variantes distintas (sin repeticion).
        """
        return tuple(
            self._signal(round_index, variant) for variant in range(self._config.pool_size)
        )

    def run_round(
        self, round_index: int, hypotheses: Sequence[str] | None = None
    ) -> RoundReport:
        """Ejecuta una ronda: hipotesis -> AST -> gates -> eval -> zoo.

        Args:
            round_index: Ronda de mineria.
            hypotheses: Hipotesis explicitas; si se omiten usa DPI.

        Returns:
            Reporte con aceptadas y rechazadas (formula, razon).
        """
        plans = tuple(hypotheses) if hypotheses else self.diversified_init(round_index)
        accepted: list[ZooEntry] = []
        rejected: list[tuple[str, str]] = []
        for hypothesis in plans:
            context = self._context(hypothesis, round_index)
            entry, formula, reason = self._process(context)
            if entry is not None:
                accepted.append(entry)
            else:
                rejected.append((formula, reason))
                self._remember(reason)
        return RoundReport(accepted=tuple(accepted), rejected=tuple(rejected))

    def search_mcts(self, seed: Expr, iterations: int) -> MCTSResult:
        """Busqueda MCTS-UCT sobre formulas guiada por backtest (AlphaMCTS).

        El seed se evalua en la raiz; mientras un nodo tenga capacidad
        (menos de ``branching`` hijos) expande ahi mismo — creando hermanos
        compitientes — y solo desciende por el hijo UCT cuando el nodo ya
        esta lleno; backpropaga el score. Determinista: mismo estado + hooks
        => mismo resultado (sin azar; empates UCT -> primer maximo).

        Args:
            seed: Formula inicial.
            iterations: Expansiones a realizar.

        Returns:
            Mejor formula, score, visitas y aceptadas de la busqueda.
        """
        root = _Node(seed)
        accepted: list[str] = []
        self._evaluate_into(root, accepted)
        for _ in range(iterations):
            node = root
            while node.children and len(node.children) >= self._config.branching:
                node = _uct_select(node, self._config.exploration)
            child = _Node(self._expand_expr(node), parent=node)
            self._evaluate_into(child, accepted)
            node.children.append(child)
            _backprop(child)
        best = _best_node(root)
        return MCTSResult(
            best=best.expr,
            best_score=best.score,
            visited=iterations,
            accepted=tuple(accepted),
        )

    @staticmethod
    def evolve_pool(
        pool: Sequence[Trajectory], reflect_hook: ReflectHook
    ) -> tuple[Trajectory, ...]:
        """Evoluciona un pool: crossover por pares + mutacion del peor.

        Args:
            pool: Trayectorias actuales (no vacias para mutar).
            reflect_hook: Reflexion para la mutacion segment-local.

        Returns:
            Pool de descendientes: ``len(pool)//2`` crossovers (pares por
            recompensa) + 1 mutacion del peor.
        """
        ranked = sorted(pool, key=lambda t: (-t.reward, t.hypothesis))
        offspring = list(map(crossover, ranked[0::2], ranked[1::2]))
        if ranked:
            offspring.append(mutate(ranked[-1], reflect_hook))
        return tuple(offspring)

    def _context(self, hypothesis: str, round_index: int) -> MiningContext:
        """Construye el contexto de iteracion con feedback reciente."""
        return MiningContext(
            hypothesis=hypothesis,
            round_index=round_index,
            forbidden_genes=frozenset(self._config.forbidden_genes),
            feedback=tuple(self._feedback[-MAX_FEEDBACK:]),
            max_nodes=self._config.max_nodes,
        )

    def _process(self, context: MiningContext) -> tuple[ZooEntry | None, str, str]:
        """Procesa una hipotesis: genera, gatea, evalua y deposita.

        Returns:
            (entrada, formula, razon): entrada no-nula si acepto; en
            rechazo, formula canonica (vacio si fallo la generacion) y
            razon legible.
        """
        try:
            expr = parse_expr(self._construct(context, context.hypothesis))
        except ValueError as exc:
            return None, "", f"generacion: {exc}"
        formula = to_formula(expr)
        gate_reason = self._gate(expr, context.hypothesis)
        if gate_reason:
            self.zoo.record_failure(formula, _gate_mode(gate_reason))
            return None, formula, gate_reason
        verdict = evaluate_factor(expr, self.panel, min_abs_ic=self._config.ic_threshold)
        if not verdict.accepted:
            self.zoo.record_failure(formula, "metricas")
            return None, formula, f"metricas: {'; '.join(verdict.reasons)}"
        entry = ZooEntry(
            formula=formula,
            tree=to_dict(expr),
            family=classify_family(expr),
            score=verdict.score,
            rank_ic=verdict.metrics.rank_ic,
            round_index=context.round_index,
        )
        if not self.zoo.add(entry, min_originality=self._config.min_originality):
            self.zoo.record_failure(formula, "originalidad")
            return None, formula, "originalidad: duplicado o demasiado similar al zoo"
        return entry, formula, ""

    def _gate(self, expr: Expr, hypothesis: str) -> str:
        """Gates baratos antes del eval (complejidad/fsa/originalidad/alineacion)."""
        nodes = complexity(expr)
        if nodes > self._config.max_nodes:
            return f"complejidad: {nodes} nodos > maximo {self._config.max_nodes}"
        if violates_fsa(expr, self._config.forbidden_genes):
            return "fsa: motif abstracto en el conjunto prohibido (crowding)"
        if self.zoo.is_similar(expr, min_originality=self._config.min_originality):
            return "originalidad: duplicado o demasiado similar al zoo"
        if self._align is not None:
            score = self._align(hypothesis, to_formula(expr))
            if score < ALIGNMENT_MIN:
                return f"alineacion: score {score:.2f} < minimo {ALIGNMENT_MIN:.2f}"
        return ""

    def _remember(self, reason: str) -> None:
        """Arrastra el rechazo al feedback de las siguientes iteraciones."""
        if reason:
            self._feedback.append(reason)
            del self._feedback[:-MAX_FEEDBACK]

    def _evaluate_into(self, node: _Node, accepted: list[str]) -> None:
        """Evalua el expr del nodo y acumula aceptadas (verdad = metricas)."""
        verdict = evaluate_factor(
            node.expr, self.panel, min_abs_ic=self._config.ic_threshold
        )
        node.verdict = verdict
        node.score = verdict.score if verdict.accepted else 0.0
        if verdict.accepted:
            accepted.append(to_formula(node.expr))
            self.zoo.add(
                ZooEntry(
                    formula=to_formula(node.expr),
                    tree=to_dict(node.expr),
                    family=classify_family(node.expr),
                    score=verdict.score,
                    rank_ic=verdict.metrics.rank_ic,
                    round_index=0,
                ),
                min_originality=self._config.min_originality,
            )

    def _expand_expr(self, node: _Node) -> Expr:
        """Expansion del nodo: construct_hook con su formula como blueprint."""
        blueprint = to_formula(node.expr)
        feedback = node.verdict.reasons if node.verdict else ()
        context = MiningContext(
            hypothesis=blueprint,
            round_index=0,
            forbidden_genes=frozenset(self._config.forbidden_genes),
            feedback=feedback,
            max_nodes=self._config.max_nodes,
        )
        try:
            return parse_expr(self._construct(context, blueprint))
        except ValueError:
            logger.info("mining_loop: expansion invalida de '%s'; hijo muerto", blueprint)
            return node.expr


class _Node:
    """Nodo MCTS mutable (visits/value/backprop)."""

    __slots__ = ("children", "expr", "parent", "score", "value", "verdict", "visits")

    def __init__(self, expr: Expr, parent: _Node | None = None) -> None:
        self.expr = expr
        self.parent = parent
        self.children: list[_Node] = []
        self.verdict: EvalVerdict | None = None
        self.score = 0.0
        self.visits = 0
        self.value = 0.0


def _uct_select(node: _Node, exploration: float) -> _Node:
    """Selecciona el hijo UCT; determinista: primer maximo en orden."""
    best_child: _Node | None = None
    best_uct = -float("inf")
    log_parent = math.log(node.visits + 1)
    for child in node.children:
        if child.visits == 0:
            return child
        uct = child.value / child.visits + exploration * math.sqrt(
            log_parent / child.visits
        )
        if uct > best_uct:
            best_uct = uct
            best_child = child
    return best_child if best_child is not None else node


def _backprop(node: _Node) -> None:
    """Propaga el score del nodo hacia la raiz (visits + value)."""
    cursor: _Node | None = node
    while cursor is not None:
        cursor.visits += 1
        cursor.value += node.score
        cursor = cursor.parent


def _best_node(root: _Node) -> _Node:
    """Mejor nodo por score propio; determinista: primer maximo DFS."""
    best = root
    stack = [root]
    while stack:
        node = stack.pop()
        if node.score > best.score:
            best = node
        stack.extend(reversed(node.children))
    return best


def _gate_mode(reason: str) -> str:
    """Extrae el modo de fallo del prefijo de una razon de gate."""
    return reason.split(":", 1)[0]
