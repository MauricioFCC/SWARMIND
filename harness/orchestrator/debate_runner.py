"""
DebateRunner — logica de debate extraida de TaskOrchestrator (ADR-0017).

Contiene la logica autocontenida de ``run_debate`` y sus metodos
relacionados, delegando la ejecucion a DebateOrchestrator.

Uso:
    runner = DebateRunner(store, session_ctx, bus)
    result = runner.run_debate(session_id, task, agents, strategy, dispatch_fn)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from harness.orchestrator.debate_orchestrator import (
    CONVERGENCE_THRESHOLD,
    DebateOrchestrator,
    DebateResult,
    DebateStrategy,
)
from harness.orchestrator.minority_sentinel import MinoritySentinel
from harness.orchestrator.structured_log import StructuredLogRecord

logger = logging.getLogger(__name__)

#: Variable de entorno (opt-out) que DESACTIVA el ``MinoritySentinel``.
#: Default ON: la mayoria revertible (ACL 2026) es una mejora de frontera que
#: no cambia la interfaz publica del debate.
ENV_MINORITY_SENTINEL = "SWARMIND_MINORITY_SENTINEL"

#: Valores (case-insensitive) que desactivan el sentinel.
_ENV_FALSY = frozenset({"0", "false", "no", "off"})

#: Marca para distinguir "no inyectado por DI" de "inyectado explicitamente
#: None" (que desactiva el sentinel). WHY: el default del constructor debe
#: resolver por entorno, pero DI explicita siempre gana.
_UNSET: Any = object()


def _sentinel_enabled() -> bool:
    """Indica si el ``MinoritySentinel`` debe activarse por defecto.

    Politica opt-out (12-Factor): env ausente o vacia -> activo; cualquier
    valor en ``_ENV_FALSY`` (``0``/``false``/``no``/``off``) -> desactivado.

    Returns:
        ``True`` si el sentinel debe inyectarse por defecto; ``False`` si
        ``SWARMIND_MINORITY_SENTINEL`` lo desactiva.
    """
    raw = os.getenv(ENV_MINORITY_SENTINEL)
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() not in _ENV_FALSY


def _resolve_sentinel(sentinel: Any = _UNSET) -> MinoritySentinel | None:
    """Resuelve el sentinel del debate (DI > env default ON > None).

    Args:
        sentinel: Instancia inyectada por DI; ``None`` lo desactiva
            explicitamente; ``_UNSET`` (default) delega en la politica por
            entorno.

    Returns:
        La instancia inyectada, o un ``MinoritySentinel`` nuevo si el default
        por entorno esta activo, o ``None`` si esta desactivado.
    """
    if sentinel is not _UNSET:
        return sentinel
    return MinoritySentinel() if _sentinel_enabled() else None


class DebateRunner:
    """
    Ejecuta debates multi-agente delegando en DebateOrchestrator.

    Extraido de TaskOrchestrator para reducir el tamano del modulo
    principal (ADR-0017 / <900LC).

    Attributes:
        _store: LanceVectorStore opcional para persistencia.
        _session_ctx: SessionContext para acceso a sesiones activas.
        _bus: AgentBus o AsyncAgentBus para comunicacion entre agentes.
    """

    def __init__(
        self,
        store: Any,
        session_ctx: Any,
        bus: Any,
        sentinel: Any = _UNSET,
    ) -> None:
        """
        Args:
            store: LanceVectorStore o None. Se pasa a DebateOrchestrator.
            session_ctx: SessionContext para resolver sesiones.
            bus: AgentBus para logging de comunicacion entre agentes.
            sentinel: ``MinoritySentinel`` inyectado por DI. Por defecto se
                crea uno nuevo salvo que ``SWARMIND_MINORITY_SENTINEL`` lo
                desactive; pasar ``None`` lo desactiva explicitamente
                (backward-compat con el comportamiento previo).
        """
        self._store = store
        self._session_ctx = session_ctx
        self._bus = bus
        self._sentinel = _resolve_sentinel(sentinel)

    def _build_orchestrator(self) -> DebateOrchestrator:
        """Construye el ``DebateOrchestrator`` con el sentinel resuelto.

        WHAT: inyecta el ``MinoritySentinel`` (DI/env) al construir el
        orquestador de debate. WHY: sin este cableado la revision de minoria
        quedaba inactiva (``sentinel=None``). WHERE: ``run_debate`` y
        ``run_debate_async``.

        Returns:
            ``DebateOrchestrator`` con ``vector_store`` y ``sentinel``
            (``None`` => comportamiento legacy sin reversion).
        """
        return DebateOrchestrator(
            vector_store=self._store, sentinel=self._sentinel,
        )

    def run_debate(
        self,
        session_id: str,
        task: str,
        agents: list[str] | None = None,
        strategy: str = "consensus",
        dispatch_fn: callable | None = None,
    ) -> DebateResult:
        """
        Ejecuta un debate multi-agente para una sesion con plantilla debate.

        Obtiene la sesion de SessionContext, resuelve los agentes
        participantes, mapea la estrategia a DebateStrategy y delega
        la ejecucion a DebateOrchestrator.

        Args:
            session_id: ID de la sesion activa.
            task: Tarea original a debatir.
            agents: Lista de nombres de agentes. Si es None, se extraen
                del plan de la sesion (excluyendo ``coordinator``).
            strategy: Estrategia de debate: ``'consensus'``, ``'critique'``
                o ``'deliberation'``. Por defecto ``'consensus'``.
            dispatch_fn: Callable opcional para obtener respuestas de
                agentes. Si se omite, DebateOrchestrator usa un fallback
                interno.

        Returns:
            DebateResult con el resultado completo del debate.

        Raises:
            ValueError: Si la sesion ``session_id`` no existe.
        """
        agents, debate_strategy = self._prepare(session_id, agents, strategy)

        # Ejecutar debate (ruta sync) con el sentinel resuelto (DI/env).
        orch = self._build_orchestrator()
        result = orch.debate(
            task=task,
            agents=agents,
            strategy=debate_strategy,
            dispatch_fn=dispatch_fn,
        )

        self._log_completed(session_id, strategy, agents, result)
        return result

    async def run_debate_async(
        self,
        session_id: str,
        task: str,
        agents: list[str] | None = None,
        strategy: str = "consensus",
        dispatch_fn: callable | None = None,
        convergence_threshold: float = CONVERGENCE_THRESHOLD,
    ) -> DebateResult:
        """
        Ejecuta un debate multi-agente por la ruta asincrona.

        Equivale a ``run_debate`` pero usa ``DebateOrchestrator.debate_async``:
        para ``consensus`` aprovecha el dispatch paralelo nativo (PaCoRe, O(n)
        -> O(1)); para ``critique``/``deliberation`` delega en la ruta sync via
        ``asyncio.to_thread``. ``run_debate`` (sync) permanece sin cambios.

        Args:
            session_id: ID de la sesion activa.
            task: Tarea original a debatir.
            agents: Lista de agentes. Si es None se extraen del plan de la
                sesion (excluyendo ``coordinator``).
            strategy: ``'consensus'``, ``'critique'`` o ``'deliberation'``.
            dispatch_fn: Callable opcional ``(agent, task, context) -> str``.
            convergence_threshold: Umbral de convergencia del consenso async.

        Returns:
            DebateResult con el resultado completo del debate.

        Raises:
            ValueError: Si la sesion ``session_id`` no existe.
        """
        agents, debate_strategy = self._prepare(session_id, agents, strategy)

        orch = self._build_orchestrator()
        result = await orch.debate_async(
            task=task,
            agents=agents,
            strategy=debate_strategy,
            dispatch_fn=dispatch_fn,
            convergence_threshold=convergence_threshold,
        )

        self._log_completed(session_id, strategy, agents, result)
        return result

    def _prepare(
        self,
        session_id: str,
        agents: list[str] | None,
        strategy: str,
    ) -> tuple[list[str], DebateStrategy]:
        """
        Resuelve la sesion, los agentes y la estrategia de un debate.

        Args:
            session_id: ID de la sesion activa.
            agents: Agentes explicitos o None para extraerlos del plan.
            strategy: Nombre de estrategia (``consensus``/``critique``/
                ``deliberation``).

        Returns:
            Tupla ``(agents, debate_strategy)``.

        Raises:
            ValueError: Si la sesion ``session_id`` no existe.
        """
        session = self._session_ctx.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found.")

        if agents is None:
            agents = sorted({
                st.agent for st in session.plan.subtasks
                if st.agent != "coordinator"
            })

        strategy_map: dict[str, DebateStrategy] = {
            "consensus": DebateStrategy.CONSENSUS,
            "critique": DebateStrategy.CRITIQUE,
            "deliberation": DebateStrategy.DELIBERATION,
        }
        return agents, strategy_map.get(strategy, DebateStrategy.CONSENSUS)

    def _log_completed(
        self,
        session_id: str,
        strategy: str,
        agents: list[str],
        result: DebateResult,
    ) -> None:
        """Registra en el log estructurado el resultado de un debate."""
        StructuredLogRecord.info(
            "debate_completed",
            message=(
                f"Debate completado para sesion {session_id}: "
                f"confianza={result.confidence:.2f}, "
                f"acuerdo={result.agent_agreement:.2f}"
            ),
            session_id=session_id,
            strategy=strategy,
            agents=agents,
            confidence=round(result.confidence, 4),
            agreement=round(result.agent_agreement, 4),
            num_rounds=len(result.rounds),
        )
