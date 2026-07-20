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
from typing import Any, Dict, List, Optional

from harness.orchestrator.debate_orchestrator import (
    DebateOrchestrator,
    DebateResult,
    DebateStrategy,
)
from harness.orchestrator.structured_log import StructuredLogRecord

logger = logging.getLogger(__name__)


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

    def __init__(self, store: Any, session_ctx: Any, bus: Any) -> None:
        """
        Args:
            store: LanceVectorStore o None. Se pasa a DebateOrchestrator.
            session_ctx: SessionContext para resolver sesiones.
            bus: AgentBus para logging de comunicacion entre agentes.
        """
        self._store = store
        self._session_ctx = session_ctx
        self._bus = bus

    def run_debate(
        self,
        session_id: str,
        task: str,
        agents: Optional[List[str]] = None,
        strategy: str = "consensus",
        dispatch_fn: Optional[callable] = None,
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
        session = self._session_ctx.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found.")

        # Resolver agentes del plan si no se proporcionaron
        if agents is None:
            agents = sorted({
                st.agent for st in session.plan.subtasks
                if st.agent != "coordinator"
            })

        # Mapear estrategia
        strategy_map: Dict[str, DebateStrategy] = {
            "consensus": DebateStrategy.CONSENSUS,
            "critique": DebateStrategy.CRITIQUE,
            "deliberation": DebateStrategy.DELIBERATION,
        }
        debate_strategy = strategy_map.get(strategy, DebateStrategy.CONSENSUS)

        # Ejecutar debate
        orch = DebateOrchestrator(vector_store=self._store)
        result = orch.debate(
            task=task,
            agents=agents,
            strategy=debate_strategy,
            dispatch_fn=dispatch_fn,
        )

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

        return result
