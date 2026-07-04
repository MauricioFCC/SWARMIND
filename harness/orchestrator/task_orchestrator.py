"""
Task Orchestrator — Plan-and-Execute with DAG parallelism.

Central piece that connects TaskPlanner → SessionContext → AgentBus → Dispatch.

Flow for ANY user message:
  1. RECEIVE: User sends message (with or without @agent)
  2. PLAN: TaskPlanner decomposes into DAG of subtasks
  3. TRACK: SessionContext preserves state
  4. COMMUNICATE: AgentBus notifies all relevant agents
  5. DISPATCH: For each ready subtask, prepare context with:
       - Plan overview (all subtasks, dependencies, status)
       - Previous subtask results
       - Current subtask instructions
       - Agent-specific skill context
  6. EXECUTE: LLM receives the full structured context and produces results
  7. VERIFY: Coordinator checks completion, updates session, repeats

Key design decisions:
  - Parallel: subtasks at the same dependency level execute SIMULTANEOUSLY
  - Sequential: subtasks with dependencies wait for predecessors
  - Communication: results are broadcast to all agents via AgentBus
  - Never lost: full session state persisted to LanceDB
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from harness.orchestrator.agent_bus import AgentBus
from harness.orchestrator.task_planner import TaskPlan, TaskPlanner
from harness.orchestrator.session_context import SessionContext, SessionState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class OrchestratorResult:
    """
    Result of processing a message through the orchestrator.

    Contains everything the LLM needs to execute: the plan, current level,
    previous results, agent assignments, and communication history.
    """
    session_id: str
    target_agent: str           # Primary agent for this dispatch
    plan: TaskPlan
    current_level: List[Dict]    # Subtasks ready for execution
    previous_results: List[Dict] # Completed subtask results
    session_status: str          # Human-readable status
    communication_log: List[Dict] # Recent agent communications
    original_message: str
    is_new_plan: bool            # Whether a new plan was created
    is_complete: bool            # Whether the entire plan is done

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "target_agent": self.target_agent,
            "plan": self.plan.to_dict(),
            "current_level": self.current_level,
            "previous_results": self.previous_results,
            "session_status": self.session_status,
            "communication_log": self.communication_log,
            "original_message": self.original_message,
            "is_new_plan": self.is_new_plan,
            "is_complete": self.is_complete,
        }


# ---------------------------------------------------------------------------
# TaskOrchestrator
# ---------------------------------------------------------------------------

class TaskOrchestrator:
    """
    Orchestrates multi-agent task execution with Plan-and-Execute.

    Usage:
        orch = TaskOrchestrator()
        result = orch.process_message("implementa una API REST en Rust")

        # result.plan contains the full DAG
        # result.current_level has subtasks ready to execute
        # result.session_status shows progress
        # result.communication_log has agent messages
    """

    def __init__(
        self,
        vector_store: Optional[Any] = None,
    ) -> None:
        """
        Args:
            vector_store: LanceVectorStore instance for persistence.
        """
        self._store = vector_store
        self._planner = TaskPlanner()
        self._session_ctx = SessionContext(vector_store)
        self._bus = AgentBus(vector_store=vector_store)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_message(
        self,
        message: str,
        force_agent: Optional[str] = None,
    ) -> OrchestratorResult:
        """
        Process a user message through the full orchestration pipeline.

        Args:
            message: The user's message.
            force_agent: Optional forced agent (if user used @agent).

        Returns:
            OrchestratorResult with plan, context, and execution state.
        """
        # --- 1. Determine if this is a continuation or new task ---
        active_session = self._session_ctx.get_active()

        if self._is_continuation(message, active_session):
            # User is continuing previous work — use existing plan
            return self._handle_continuation(message, active_session, force_agent)

        # --- 2. New task — decompose into plan ---
        plan = self._planner.decompose(message)
        session = self._session_ctx.get_or_create(message, plan)

        # --- 3. Notify agents via bus ---
        self._broadcast_plan(session)

        # --- 4. Prepare execution context ---
        return self._build_result(session, message, force_agent, is_new_plan=True)

    def process_completion(
        self,
        session_id: str,
        subtask_id: str,
        result: str,
    ) -> OrchestratorResult:
        """
        Process a subtask completion.

        Called when an agent reports that a subtask is done.
        Updates the session state and returns the next step.

        Args:
            session_id: The session ID.
            subtask_id: The completed subtask ID.
            result: The result/artifact from the subtask.

        Returns:
            OrchestratorResult for the next execution step.
        """
        session = self._session_ctx.get_session(session_id)
        if not session:
            logger.warning("Session %s not found for completion.", session_id)
            return self._empty_result()

        self._session_ctx.mark_subtask_done(session, subtask_id, result)

        # Notify agents
        self._broadcast_completion(session, subtask_id, result)

        # If complete, celebrate
        if session.plan.is_complete():
            self._broadcast_complete(session)
            return self._build_result(
                session, session.original_message, None, is_new_plan=False,
            )

        # Return next level
        return self._build_result(
            session, session.original_message, None, is_new_plan=False,
        )

    def get_summary(self, session_id: Optional[str] = None) -> str:
        """Get a human-readable summary of session progress."""
        if session_id:
            session = self._session_ctx.get_session(session_id)
        else:
            session = self._session_ctx.get_active()

        if not session:
            return "❌ No hay sesiones activas."

        return self._session_ctx.get_status(session)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _is_continuation(self, message: str, session: Optional[SessionState]) -> bool:
        """
        Determine if a message is continuing previous work.

        A continuation is when:
          - There's an active session with incomplete tasks
          - The message doesn't start a completely new task
          - The message references previous work ("continuar", "siguiente", etc.)
        """
        if not session or session.completed:
            return False

        msg_lower = message.lower()
        continuation_keywords = [
            "continuar", "continue", "siguiente", "next", "sigue",
            "proceder", "proceed", "avanzar", "adelante",
            "terminar", "finish", "completar", "complete",
            "paso", "step", "sigue con",
        ]

        for kw in continuation_keywords:
            if kw in msg_lower:
                return True

        # If message is very short (< 10 chars), likely continuation
        if len(message.strip()) < 10:
            return True

        return False

    def _handle_continuation(
        self,
        message: str,
        session: SessionState,
        force_agent: Optional[str],
    ) -> OrchestratorResult:
        """Handle a continuation message (user wants to proceed)."""
        self._session_ctx.add_message(session, "user", message)
        return self._build_result(
            session, message, force_agent, is_new_plan=False,
        )

    def _build_result(
        self,
        session: SessionState,
        message: str,
        force_agent: Optional[str],
        is_new_plan: bool,
    ) -> OrchestratorResult:
        """Build the OrchestratorResult from session state."""

        plan = session.plan
        next_level = plan.get_next_level()

        # Determine primary target agent for this dispatch
        target_agent = force_agent or self._resolve_target_agent(next_level)

        # Format current level for output
        current_level = []
        for st in next_level:
            current_level.append({
                "id": st.id,
                "agent": st.agent,
                "description": st.description,
                "expected_output": st.expected_output,
                "context_hint": st.context_hint,
                "dependencies": st.dependencies,
            })

        # Format previous results
        previous_results = []
        for st in plan.subtasks:
            if st.completed and st.result:
                previous_results.append({
                    "id": st.id,
                    "agent": st.agent,
                    "description": st.description,
                    "result": st.result,
                })

        # Get communication log
        comm_log = self._bus.get_channel_history(
            f"#session-{session.session_id}", limit=20
        )

        status = self._session_ctx.get_status(session)

        return OrchestratorResult(
            session_id=session.session_id,
            target_agent=target_agent,
            plan=plan,
            current_level=current_level,
            previous_results=previous_results,
            session_status=status,
            communication_log=comm_log,
            original_message=message,
            is_new_plan=is_new_plan,
            is_complete=plan.is_complete(),
        )

    def _resolve_target_agent(self, next_level: List) -> str:
        """Determine the primary agent for the current dispatch."""
        if not next_level:
            return "coordinator"

        # Get unique agents in this level
        agents = {st.agent for st in next_level}

        # If all go to same agent, return it
        if len(agents) == 1:
            return agents.pop()

        # Multiple agents — return coordinator (will dispatch to each)
        return "coordinator"

    def _broadcast_plan(self, session: SessionState) -> None:
        """Broadcast the new plan to all involved agents."""
        try:
            # Get unique agents
            agents = set()
            for st in session.plan.subtasks:
                agents.add(f"@{st.agent}")

            summary = session.plan.get_summary()

            # Post to session channel
            self._bus.post_message(
                channel=f"#session-{session.session_id}",
                from_agent="@coordinator",
                to_agent="@all",
                message=(
                    f"📋 **NUEVO PLAN**\n\n"
                    f"Tarea: {session.original_message[:120]}\n"
                    f"Agentes involucrados: {', '.join(sorted(agents))}\n\n"
                    f"{summary}"
                ),
                message_type="notification",
            )

            # Notify each agent individually
            for agent in agents:
                self._bus.post_message(
                    channel=f"#session-{session.session_id}",
                    from_agent="@coordinator",
                    to_agent=agent,
                    message=(
                        f"Asignado al plan `{session.session_id}`.\n"
                        f"Revisa la sección de tu nivel para saber cuándo empezar."
                    ),
                    message_type="request",
                )

            logger.info(
                "Plan %s broadcast to %d agents.",
                session.session_id, len(agents),
            )
        except Exception as exc:
            logger.warning("Broadcast plan error: %s", exc)

    def _broadcast_completion(
        self,
        session: SessionState,
        subtask_id: str,
        result: str,
    ) -> None:
        """Broadcast a subtask completion to all agents."""
        try:
            # Find the subtask
            subtask = next(
                (s for s in session.plan.subtasks if s.id == subtask_id),
                None,
            )
            if not subtask:
                return

            # Notify
            self._bus.post_message(
                channel=f"#session-{session.session_id}",
                from_agent=f"@{subtask.agent}",
                to_agent="@all",
                message=(
                    f"✅ **Subtask {subtask_id} COMPLETADA**\n"
                    f"Agente: @{subtask.agent}\n"
                    f"Qué: {subtask.description}\n"
                    f"Resultado: {result[:200]}"
                ),
                message_type="response",
            )

            # If there are agents waiting on this dependency, notify them
            waiting = [
                s for s in session.plan.subtasks
                if not s.completed and subtask_id in s.dependencies
            ]
            for st in waiting:
                self._bus.post_message(
                    channel=f"#session-{session.session_id}",
                    from_agent="@coordinator",
                    to_agent=f"@{st.agent}",
                    message=(
                        f"Tu dependencia `{subtask_id}` ha sido completada.\n"
                        f"Ahora puedes comenzar: **{st.description}**"
                    ),
                    message_type="notification",
                )

        except Exception as exc:
            logger.warning("Broadcast completion error: %s", exc)

    def _broadcast_complete(self, session: SessionState) -> None:
        """Broadcast that the entire plan is complete."""
        try:
            # Collect all results
            results_summary = []
            for st in session.plan.subtasks:
                status = "✅" if st.completed else "❌"
                results_summary.append(
                    f"{status} [{st.agent}] {st.description}"
                )

            self._bus.post_message(
                channel=f"#session-{session.session_id}",
                from_agent="@coordinator",
                to_agent="@all",
                message=(
                    f"🎉 **PLAN COMPLETO**\n\n"
                    f"Sesión: {session.session_id}\n"
                    f"Tarea original: {session.original_message[:120]}\n\n"
                    + "\n".join(results_summary)
                ),
                message_type="notification",
            )
        except Exception as exc:
            logger.warning("Broadcast complete error: %s", exc)

    def _empty_result(self) -> OrchestratorResult:
        """Return an empty result (error case)."""
        from harness.orchestrator.task_planner import TaskPlan
        plan = TaskPlan(session_id="error", original_message="")
        return OrchestratorResult(
            session_id="error",
            target_agent="coordinator",
            plan=plan,
            current_level=[],
            previous_results=[],
            session_status="❌ Error: sesión no encontrada",
            communication_log=[],
            original_message="",
            is_new_plan=False,
            is_complete=False,
        )
