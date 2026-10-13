"""wiring.py — cableado de frontera del ``TaskOrchestrator`` (telemetria + router).

WHAT: resuelve y mantiene el estado de los dos componentes de frontera que
existian standalone y no estaban unidos al flujo real: ``TokenTelemetry``
(telemetria de tokens, activa por defecto con opt-out) y ``PipelineRouter``
(cascada de triage SLM -> heuristica -> frontier, opt-in por entorno). WHY:
mantener ``orchestrator.py`` bajo el limite AGR (<500 lineas) y aislar la
logica de DI/flags (SRP/KISS). WHERE: ``TaskOrchestrator.__init__`` (construye
el wiring) y ``TaskOrchestrator.process_message`` (clasifica y registra).

Politica de flags (12-Factor, EDV):
    - ``SWARMIND_TELEMETRY_DISABLE`` (opt-out): truthy desactiva la telemetria;
      ausente -> telemetria ACTIVA por defecto.
    - ``SWARMIND_PIPELINE_ROUTER`` (opt-in): truthy activa la cascada; ausente o
      ``0`` -> comportamiento legacy (``TaskPlanner``). Opt-in deliberado para
      NO cambiar el flujo ya probado sin evidencia.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from harness.common import estimate_tokens
from harness.observability.token_telemetry import TokenTelemetry

logger = logging.getLogger(__name__)

#: Variable de entorno (opt-out) que desactiva la telemetria del orquestador.
ENV_TELEMETRY_DISABLE = "SWARMIND_TELEMETRY_DISABLE"

#: Variable de entorno (opt-in) que activa la cascada ``PipelineRouter``.
ENV_PIPELINE_ROUTER = "SWARMIND_PIPELINE_ROUTER"

#: Rol con el que el orquestador registra su uso de tokens.
ORCHESTRATOR_ROLE = "orchestrator"

#: Tokens de salida fijos por despacho de plan (una decision de orquestacion).
ORCHESTRATOR_OUTPUT_TOKENS = 1

#: Valores (case-insensitive) que se consideran "activos" para una env booleana.
_ENV_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_truthy(name: str) -> bool:
    """Indica si la variable de entorno ``name`` tiene un valor afirmativo.

    Args:
        name: Nombre de la variable de entorno.

    Returns:
        ``True`` si el valor (normalizado) esta en ``_ENV_TRUTHY``; ``False`` si
        esta ausente o tiene cualquier otro valor (p. ej. ``"0"``).
    """
    return os.getenv(name, "").strip().lower() in _ENV_TRUTHY


def resolve_telemetry(telemetry: TokenTelemetry | None) -> TokenTelemetry | None:
    """Resuelve la telemetria del orquestador (DI > env opt-out > default ON).

    Args:
        telemetry: Instancia inyectada por DI; si es ``None`` se aplica la
            politica por entorno.

    Returns:
        La telemetria inyectada si se proveyo; ``None`` si
        ``SWARMIND_TELEMETRY_DISABLE`` esta activa; en cualquier otro caso una
        ``TokenTelemetry`` nueva (default activo).
    """
    if telemetry is not None:
        return telemetry
    if _env_truthy(ENV_TELEMETRY_DISABLE):
        return None
    return TokenTelemetry()


def pipeline_router_enabled() -> bool:
    """Indica si la cascada ``PipelineRouter`` esta activa (opt-in por env).

    Returns:
        ``True`` solo si ``SWARMIND_PIPELINE_ROUTER`` tiene valor afirmativo.
    """
    return _env_truthy(ENV_PIPELINE_ROUTER)


class WorkflowWiring:
    """Estado del cableado de frontera del orquestador (telemetria + router).

    Attributes:
        _telemetry: Acumulador de tokens activo (o ``None`` si esta apagado).
        _pipeline_router: Router inyectado (DI) o construido en el primer uso.
        _last_routing_decision: Ultima ``RoutingDecision`` (observabilidad).
    """

    def __init__(
        self,
        *,
        telemetry: TokenTelemetry | None = None,
        pipeline_router: Any | None = None,
    ) -> None:
        """Inicializa el wiring con DI (kw-only) y defaults por entorno.

        Args:
            telemetry: Telemetria inyectada; ``None`` delega en
                :func:`resolve_telemetry`.
            pipeline_router: Router inyectado (DI); ``None`` construye el
                ``PipelineRouter`` real de forma perezosa al primer uso activo.
        """
        self._telemetry: TokenTelemetry | None = resolve_telemetry(telemetry)
        self._pipeline_router: Any | None = pipeline_router
        self._last_routing_decision: Any | None = None

    @property
    def telemetry(self) -> TokenTelemetry | None:
        """Telemetria activa del orquestador (o ``None`` si esta apagada)."""
        return self._telemetry

    @property
    def last_routing_decision(self) -> Any | None:
        """Ultima decision de ruteo (``None`` si la cascada esta apagada)."""
        return self._last_routing_decision

    def classify(self, message: str) -> Any | None:
        """Clasifica ``message`` con la cascada ``PipelineRouter`` (opt-in).

        WHAT: solo actua si ``SWARMIND_PIPELINE_ROUTER`` esta activa; en caso
        contrario devuelve ``None`` y el flujo legacy (``TaskPlanner``) sigue
        mandando. WHY: la cascada aprende ruteo que debe ejecutarse en el
        pipeline real, pero activarlo sin evidencia cambiaria el flujo probado
        (EDV). WHERE: ``TaskOrchestrator.process_message``.

        Args:
            message: Tarea del usuario a clasificar.

        Returns:
            La ``RoutingDecision`` si la cascada esta activa y clasifica; ``None``
            si esta apagada o si el router falla (nunca lanza).
        """
        if not pipeline_router_enabled():
            return None
        router = self._pipeline_router
        if router is None:
            router = self._build_default_router()
            self._pipeline_router = router
        try:
            decision = router.route(message)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "wiring: WHAT: PipelineRouter no pudo clasificar el mensaje: %s. "
                "WHY: entrada invalida o componente de frontera no disponible. "
                "WHERE: WorkflowWiring.classify",
                exc,
            )
            return None
        self._last_routing_decision = decision
        self._log_decision(decision)
        return decision

    def record_usage(self, message: str, subtask_count: int) -> None:
        """Registra el uso de tokens del despacho del plan (best-effort).

        WHAT: atribuye tokens al rol ``orchestrator``: ``cached`` = subtasks del
        plan (estructura estable reutilizable) e ``input`` = tokens del mensaje
        del turno. WHY: sin un call site real la telemetria de token economics
        no es medible (FR-2/FR-3). WHERE: ``TaskOrchestrator.process_message``.

        No hace nada si la telemetria esta apagada y nunca lanza (un fallo de
        telemetria no debe romper el flujo).

        Args:
            message: Mensaje del usuario (entrada dinamica).
            subtask_count: Numero de subtasks del plan (prefijo cacheable).
        """
        if self._telemetry is None:
            return
        cached = max(subtask_count, 0)
        dynamic = estimate_tokens(message, minimum=0)
        try:
            self._telemetry.record_usage(
                ORCHESTRATOR_ROLE,
                cached=cached,
                input=dynamic,
                output=ORCHESTRATOR_OUTPUT_TOKENS,
            )
        except (ValueError, TypeError) as exc:
            logger.warning(
                "wiring: WHAT: no se pudo registrar telemetria del orchestrator: %s. "
                "WHY: conteo invalido o rol vacio. "
                "WHERE: WorkflowWiring.record_usage",
                exc,
            )

    @staticmethod
    def _build_default_router() -> Any:
        """Construye el ``PipelineRouter`` real (import lazy, evita ciclos).

        Returns:
            Una instancia nueva de ``PipelineRouter`` con sus defaults.
        """
        from harness.orchestrator.pipeline_router import PipelineRouter
        return PipelineRouter()

    @staticmethod
    def _log_decision(decision: Any) -> None:
        """Loggea la decision de ruteo para observabilidad (best-effort).

        Args:
            decision: ``RoutingDecision`` devuelta por el router.
        """
        logger.info(
            "wiring: PipelineRouter decision pipeline=%s complexity=%s source=%s",
            getattr(decision, "pipeline", "?"),
            getattr(decision, "complexity", "?"),
            getattr(decision, "source", "?"),
        )


__all__ = [
    "ENV_PIPELINE_ROUTER",
    "ENV_TELEMETRY_DISABLE",
    "ORCHESTRATOR_OUTPUT_TOKENS",
    "ORCHESTRATOR_ROLE",
    "WorkflowWiring",
    "pipeline_router_enabled",
    "resolve_telemetry",
]
