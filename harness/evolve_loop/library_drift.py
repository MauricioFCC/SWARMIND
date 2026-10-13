"""Library Drift — retiro por OUTCOME de skill libraries auto-evolutivas.

WHAT: implementa la receta verificada de *Library Drift* (arXiv 2605.19576)
para librerias de skills que se auto-evolucionan: retiro por OUTCOME real con
``N_min`` trials de evidencia, umbral de utilidad neta ``tau``, cap activo ``C``
y prior de authoring de meta-skill. WHY: las librerias self-evolving se
degradan EN SILENCIO; el retiro agresivo (``N_min=20``) DANA la libreria
(-0.019 en la receta) porque retira skills utiles antes de acumular evidencia.
Exigir ``N_min=100`` trials estabiliza la libreria y el cap activo evita el
crecimiento sin cota. WHERE: consumidor de ``SkillUtilityTracker``
(``harness/evolve_loop/skill_utility.py``) y punto de dispatch real en
``AgentDispatcher.record_skill_outcome``.

Politica (frontera):
    - ``protect``: ``trials < N_min`` → NO se retira (evita el dano del retiro
      temprano; el componente mas valioso de la receta es NO precipitarse).
    - ``retire``: ``trials >= N_min`` y ``utilidad neta < -tau``.
    - ``keep``: ``trials >= N_min`` y ``utilidad neta >= -tau``.

Diseno:
    - ``DriftPolicy`` / ``DriftVerdict`` son ``frozen dataclass`` (IMM).
    - ``LibraryDriftManager`` recibe ``tracker`` / ``policy`` / ``skills_dir``
      por DI (kw-only); en tests se inyectan rutas temporales para NUNCA tocar
      el JSONL real ni ``.opencode/skills/auto``.
    - Best-effort: un fallo de IO loguea (WHAT+WHY+WHERE) y no rompe el loop.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from harness.evolve_loop.skill_utility import SkillUtility, SkillUtilityTracker

logger = logging.getLogger(__name__)

#: Overrides por entorno (12-Factor; sin hardcode de la politica operativa).
ENV_MIN_TRIALS = "SWARMIND_DRIFT_MIN_TRIALS"
ENV_TAU = "SWARMIND_DRIFT_TAU"
ENV_MAX_ACTIVE = "SWARMIND_DRIFT_MAX_ACTIVE"

#: N_min por defecto: trials minimos de evidencia antes de retirar (MAG).
DEFAULT_MIN_TRIALS = 100
#: tau por defecto: umbral de utilidad neta (fraccion) para retirar (MAG).
DEFAULT_TAU = 0.10
#: C por defecto: cap de skills activas antes de mandar a revision (MAG).
DEFAULT_MAX_ACTIVE = 50

#: Decisiones posibles de una evaluacion de drift.
DriftDecision = Literal["keep", "retire", "protect"]


def _env_int(name: str, default: int) -> int:
    """Lee un entero de entorno (default si ausente o invalido).

    Args:
        name: Nombre de la variable de entorno.
        default: Valor si no existe o no parsea.

    Returns:
        Entero leido o ``default``; nunca lanza.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("library_drift: %s=%r no es entero; uso %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    """Lee un flotante de entorno (default si ausente o invalido).

    Args:
        name: Nombre de la variable de entorno.
        default: Valor si no existe o no parsea.

    Returns:
        Flotante leido o ``default``; nunca lanza.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("library_drift: %s=%r no es flotante; uso %s", name, raw, default)
        return default


def _net_utility(util: SkillUtility) -> float:
    """Calcula la utilidad neta normalizada de un snapshot de skill.

    WHAT: ``(helpful - hurt) / retrievals`` en ``[-1, 1]``; ``0.0`` si aun no
    hay recuperaciones. WHY: normalizar permite comparar skills con distinto
    volumen de uso y fija ``tau=0.10`` como "10% neto de invocaciones daninas".
    WHERE: ``LibraryDriftManager.evaluate``.

    Args:
        util: Snapshot de utilidad observada del skill.

    Returns:
        Fraccion neta en ``[-1, 1]`` (``0.0`` sin recuperaciones).
    """
    if util.retrievals <= 0:
        return 0.0
    return util.net / util.retrievals


@dataclass(frozen=True)
class DriftPolicy:
    """Politica inmutable de retiro por outcome (Library Drift).

    Attributes:
        min_trials: Trials minimos de evidencia antes de poder retirar (N_min).
        tau: Umbral de utilidad neta; se retira si ``net < -tau``.
        max_active: Cap de skills activas; el excedente va a revision.

    Raises:
        ValueError: Si ``min_trials < 1``, ``max_active < 1`` o ``tau < 0``.
    """

    min_trials: int = DEFAULT_MIN_TRIALS
    tau: float = DEFAULT_TAU
    max_active: int = DEFAULT_MAX_ACTIVE

    def __post_init__(self) -> None:
        """Valida los parametros de la politica (WHAT+WHY+WHERE si viola)."""
        if self.min_trials < 1:
            raise ValueError(
                f"WHAT: min_trials invalido ({self.min_trials}). "
                "WHY: se necesita al menos 1 trial de evidencia. "
                "WHERE: DriftPolicy.__post_init__"
            )
        if self.max_active < 1:
            raise ValueError(
                f"WHAT: max_active invalido ({self.max_active}). "
                "WHY: el cap activo debe permitir al menos una skill. "
                "WHERE: DriftPolicy.__post_init__"
            )
        if self.tau < 0:
            raise ValueError(
                f"WHAT: tau invalido ({self.tau}). "
                "WHY: el umbral de utilidad neta no puede ser negativo. "
                "WHERE: DriftPolicy.__post_init__"
            )

    @classmethod
    def from_env(cls) -> DriftPolicy:
        """Construye la politica desde el entorno (defaults seguros).

        Returns:
            ``DriftPolicy`` con los overrides presentes.

        Raises:
            ValueError: Si los valores del entorno violan la validacion.
        """
        return cls(
            min_trials=_env_int(ENV_MIN_TRIALS, DEFAULT_MIN_TRIALS),
            tau=_env_float(ENV_TAU, DEFAULT_TAU),
            max_active=_env_int(ENV_MAX_ACTIVE, DEFAULT_MAX_ACTIVE),
        )


@dataclass(frozen=True)
class DriftVerdict:
    """Veredicto inmutable de drift para una skill.

    Attributes:
        name: Nombre del skill evaluado.
        trials: Trials de evidencia (recuperaciones observadas).
        net_utility: Utilidad neta normalizada en ``[-1, 1]``.
        decision: ``"keep"``, ``"retire"`` o ``"protect"``.
        reason: Motivo legible del veredicto (WHAT del porque).
    """

    name: str
    trials: int
    net_utility: float
    decision: DriftDecision
    reason: str


class LibraryDriftManager:
    """Gestiona el retiro por outcome de la libreria de skills (Library Drift).

    Attributes:
        _tracker: Tracker de utilidad observada (inyectado o por defecto).
        _policy: Politica de retiro (inyectada o por defecto).
        _retired: Acumulado de nombres retirados fisicamente por ``sweep``.
    """

    def __init__(
        self,
        *,
        tracker: SkillUtilityTracker | None = None,
        policy: DriftPolicy | None = None,
        skills_dir: Path | None = None,
    ) -> None:
        """Inicializa el manager con DI (kw-only) y defaults reales.

        Args:
            tracker: Tracker de utilidad; si es ``None`` se crea uno por
                defecto (o apuntando a ``skills_dir`` si se provee).
            policy: Politica de retiro; si es ``None`` se usa ``DriftPolicy()``.
            skills_dir: Directorio de ``.md`` auto-generados; solo se usa para
                construir el tracker por defecto cuando ``tracker`` es ``None``.
        """
        if tracker is not None:
            self._tracker = tracker
        elif skills_dir is not None:
            self._tracker = SkillUtilityTracker(skills_dir=skills_dir)
        else:
            self._tracker = SkillUtilityTracker()
        self._policy = policy if policy is not None else DriftPolicy()
        self._retired: list[str] = []

    # -- Registro de outcome real -----------------------------------------

    def record_outcome(
        self, skill_name: str, *, success: bool, used: bool = True
    ) -> None:
        """Registra el outcome real de una skill en el tracker (best-effort).

        WHAT: marca una recuperacion (si ``used``) y marca el skill como
        ``helpful`` (si ``success``) o ``hurt`` (si no). WHY: sin un consumidor
        que cablee el outcome real, ``SkillUtilityTracker`` nunca acumula
        evidencia y el retiro no puede decidirse. WHERE:
        ``AgentDispatcher.record_skill_outcome``.

        Best-effort: un fallo de IO loguea (WHAT+WHY+WHERE) y NO rompe el loop.

        Args:
            skill_name: Nombre del skill cuyo outcome se registra.
            success: ``True`` si la trayectoria que uso el skill fue correcta.
            used: ``True`` si el skill fue efectivamente recuperado/invocado.
        """
        try:
            if used:
                self._tracker.mark_retrieval(skill_name)
            if success:
                self._tracker.mark_helpful(skill_name)
            else:
                self._tracker.mark_hurt(skill_name)
        except OSError as exc:
            logger.warning(
                "library_drift: WHAT: no se pudo registrar el outcome de '%s': %s. "
                "WHY: disco lleno o permisos insuficientes al persistir el JSONL. "
                "WHERE: LibraryDriftManager.record_outcome",
                skill_name,
                exc,
            )

    # -- Evaluacion --------------------------------------------------------

    def evaluate(self, skill_name: str) -> DriftVerdict:
        """Evalua la skill contra la politica de drift (protect/retire/keep).

        WHAT: si ``trials < min_trials`` → ``protect`` (NO retiro temprano);
        si ``net < -tau`` → ``retire``; en otro caso → ``keep``. WHY: retirar
        antes de ``N_min`` trials DANA la libreria (receta Library Drift).
        WHERE: ``sweep`` y ``report``.

        Args:
            skill_name: Nombre del skill a evaluar.

        Returns:
            El ``DriftVerdict`` con la decision y su motivo.
        """
        util = self._tracker.get(skill_name)
        trials = util.retrievals
        net = _net_utility(util)
        if trials < self._policy.min_trials:
            return DriftVerdict(
                name=skill_name,
                trials=trials,
                net_utility=net,
                decision="protect",
                reason=(
                    f"trials={trials} < N_min={self._policy.min_trials}: "
                    "no se retira antes de acumular evidencia (evita el dano)"
                ),
            )
        if net < -self._policy.tau:
            return DriftVerdict(
                name=skill_name,
                trials=trials,
                net_utility=net,
                decision="retire",
                reason=(
                    f"net={net:.3f} < -tau={-self._policy.tau:.3f}: "
                    "utilidad neta negativa con evidencia suficiente"
                ),
            )
        return DriftVerdict(
            name=skill_name,
            trials=trials,
            net_utility=net,
            decision="keep",
            reason=(
                f"net={net:.3f} >= -tau={-self._policy.tau:.3f}: "
                "utilidad neta dentro del margen"
            ),
        )

    # -- Barrido y cap activo ---------------------------------------------

    def sweep(self) -> list[DriftVerdict]:
        """Evalua todas las skills y retira las que la politica marca ``retire``.

        WHAT: evalua el universo del tracker; retira fisicamente los candidatos
        via ``tracker.prune(min_retrievals=min_trials)`` (solo los que superan
        el umbral de trials) y aplica el cap activo: si quedan mas de
        ``max_active`` skills, las de peor utilidad neta van a revision (log,
        SIN borrar el seed). WHY: mantiene la libreria sana sin colapsar por
        retiro temprano ni crecer sin cota. WHERE: ciclo EVO (fase ANALYZE).

        Nota de fidelidad: el retiro fisico lo ejecuta ``tracker.prune``, cuyo
        criterio (``net < 0`` con ``retrievals >= N_min``) coincide con la regla
        de drift salvo por el margen ``tau``; la salvaguarda critica (NO retirar
        antes de ``N_min`` trials) se preserva porque ``prune`` recibe
        ``min_retrievals=min_trials``.

        Returns:
            Los ``DriftVerdict`` del universo evaluado ANTES del retiro.
        """
        verdicts = [self.evaluate(name) for name in self._tracker.names()]
        pruned = self._tracker.prune(min_retrievals=self._policy.min_trials)
        self._retired.extend(pruned)
        self._flag_cap_exceeded()
        return verdicts

    def _flag_cap_exceeded(self) -> None:
        """Manda a revision las skills peores cuando se excede el cap activo.

        WHAT: si el numero de skills activas supera ``max_active``, ordena por
        utilidad neta ascendente y loguea (WHAT+WHY+WHERE) el excedente para
        revision humana. WHY: el cap evita el crecimiento sin cota sin borrar
        skills seed (la receta retira por outcome, no por presupuesto).
        WHERE: ``LibraryDriftManager.sweep``.
        """
        remaining = [self.evaluate(name) for name in self._tracker.names()]
        excess = len(remaining) - self._policy.max_active
        if excess <= 0:
            return
        ranked = sorted(remaining, key=lambda verdict: (verdict.net_utility, verdict.name))
        for verdict in ranked[:excess]:
            logger.warning(
                "library_drift: WHAT: cap activo excedido (%d > %d); "
                "'%s' (net=%.3f) pasa a revision. "
                "WHY: mas skills activas que el cap C. "
                "WHERE: LibraryDriftManager.sweep",
                len(remaining),
                self._policy.max_active,
                verdict.name,
                verdict.net_utility,
            )

    # -- Resumen -----------------------------------------------------------

    def report(self) -> dict[str, int]:
        """Resume el estado de la libreria segun la politica de drift.

        WHAT: cuenta el universo actual por decision (``protect``/``keep``),
        los retirados acumulados por ``sweep`` y el exceso sobre el cap.
        WHY: observabilidad del drift para la fase ANALYZE. WHERE: ciclo EVO.

        Returns:
            Dict con ``total``, ``protected``, ``keep``, ``retired`` y
            ``cap_exceeded``.
        """
        verdicts = [self.evaluate(name) for name in self._tracker.names()]
        total = len(verdicts)
        protected = sum(1 for verdict in verdicts if verdict.decision == "protect")
        keep = sum(1 for verdict in verdicts if verdict.decision == "keep")
        cap_exceeded = max(0, total - self._policy.max_active)
        return {
            "total": total,
            "protected": protected,
            "keep": keep,
            "retired": len(self._retired),
            "cap_exceeded": cap_exceeded,
        }
