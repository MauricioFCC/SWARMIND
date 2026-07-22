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

Self-Healing features:
  - Circuit Breaker: open after N consecutive failures, auto-recover after timeout
  - Timeout Detection: per-level timeout kills stale execution
  - Progress Stall Detection: warns if no progress in N seconds
  - Structured Logging: all logs as JSON for centralized monitoring
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from harness.orchestrator.agent_bus import AgentBus
from harness.orchestrator.confidence_scorer import ConfidenceScore, ConfidenceScorer
from harness.orchestrator.debate_orchestrator import (
    DebateOrchestrator,
    DebateResult,
    DebateStrategy,
)
from harness.orchestrator.session_context import SessionContext, SessionState
from harness.orchestrator.task_planner import TaskPlan, TaskPlanner

logger = logging.getLogger(__name__)

from harness.orchestrator.orchestration_result import OrchestratorResult  # noqa: F401
from harness.orchestrator.self_healing import (  # noqa: F401
    CircuitBreaker,
    SelfHealingContext,
)
from harness.orchestrator.structured_log import StructuredLogRecord  # noqa: F401

# ---------------------------------------------------------------------------
# TaskOrchestrator
# ---------------------------------------------------------------------------

class TaskOrchestrator:
    """
    Orchestrates multi-agent task execution with Plan-and-Execute.

    Incorpora self-healing: circuit breaker, timeouts, stall detection,
    y logging estructurado como JSON.

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
        max_retries: int = 3,
        level_timeout_sec: float = 300.0,
        stall_timeout_sec: float = 120.0,
        verbose: bool = False,
    ) -> None:
        """
        Args:
            vector_store: LanceVectorStore instance for persistence.
            max_retries: Número máximo de reintentos por subtask fallida.
            level_timeout_sec: Timeout por nivel en segundos.
            stall_timeout_sec: Timeout de estancamiento en segundos.
            verbose: Logging detallado si True.
        """
        self._store = vector_store
        self._planner = TaskPlanner()
        self._session_ctx = SessionContext(vector_store)
        self._bus = AgentBus(vector_store=vector_store)
        self._max_retries = max_retries
        self._level_timeout_sec = level_timeout_sec
        self._stall_timeout_sec = stall_timeout_sec
        self._verbose = verbose

        # Confidence-gated early stopping
        self._confidence_scorer = ConfidenceScorer()

        # Self-healing contexts por sesión
        self._healing_contexts: Dict[str, SelfHealingContext] = {}

        # Global circuit breaker para el orquestador mismo
        self._global_cb = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
        )

        # ShapedCache para token economics (ADR-0018)
        self._shaped_cache = None

        # Idempotencia: evita procesar el mismo mensaje multiple veces
        self._recent_messages: Dict[str, float] = {}
        self._dedup_window: float = 30.0  # Ventana de 30 segundos

        StructuredLogRecord.info(
            "orchestrator_init",
            message="TaskOrchestrator inicializado",
            max_retries=max_retries,
            level_timeout_sec=level_timeout_sec,
            stall_timeout_sec=stall_timeout_sec,
            verbose=verbose,
        )

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

        Incorpora self-healing:
          - Circuit breaker global check
          - Structured logging (JSON)
          - Timeout y stall detection para sesiones activas

        Args:
            message: The user's message.
            force_agent: Optional forced agent (if user used @agent).

        Returns:
            OrchestratorResult with plan, context, and execution state.
        """
        # --- 0. Circuit breaker check ---
        if not self._global_cb.is_available:
            StructuredLogRecord.warning(
                "global_circuit_open",
                message="Circuito global abierto, rechazando mensaje",
                failures=self._global_cb.failure_count,
            )
            return self._error_result(
                "Sistema en recuperación. Intenta de nuevo en unos segundos.",
            )

        # --- 0. WAL: Write-Ahead Log para operaciones criticas ---
        if not hasattr(self, '_wal'):
            from harness.orchestrator.write_ahead_log import WriteAheadLog
            self._wal = WriteAheadLog()

        # Registrar operacion en WAL
        wal_entry = self._wal.begin(
            operation_type="process_message",
            payload={"message": message[:100], "force_agent": force_agent},
        )

        # --- 0. Verificar cache semantico (ShapedCache - Token Economics) ---
        if hasattr(self, '_shaped_cache') and self._shaped_cache is not None:
            import hashlib
            _cache_hash = hashlib.sha256((message or "").encode()).hexdigest()[:16]
            cached = self._shaped_cache.get_shaped(message, threshold=0.88)
            if cached is not None:
                response = cached.get("response", "")
                if response:
                    StructuredLogRecord.info(
                        "cache_hit",
                        message=f"Cache hit para: {message[:50]}...",
                        session_id="",
                    )
                    return OrchestratorResult(
                        session_id="",
                        target_agent="coordinator",
                        plan=None,  # type: ignore[arg-type]
                        current_level=[],
                        session_status="completed",
                        previous_results=[],
                        communication_log=[],
                        original_message=message,
                        is_new_plan=False,
                        is_complete=True,
                    )
            else:
                StructuredLogRecord.info(
                    "cache_miss",
                    message=f"Cache miss para: {message[:50]}...",
                    session_id="",
                )
                # Ajuste dinamico de threshold segun hit rate
                if hasattr(self, '_shaped_cache') and self._shaped_cache is not None:
                    try:
                        hr = float(self._shaped_cache.hit_rate)
                        current_t = float(getattr(self._shaped_cache, '_threshold', 0.88))
                        if hr > 0.9:
                            self._shaped_cache._threshold = max(0.80, current_t - 0.02)
                        elif hr < 0.5:
                            self._shaped_cache._threshold = min(0.95, current_t + 0.02)
                    except (TypeError, ValueError):
                        pass

        # --- 0. Idempotencia: evitar duplicados del mismo mensaje ---
        import hashlib
        msg_hash = hashlib.sha256((message or "").encode()).hexdigest()[:16]
        now = time.time()
        # Limpiar entradas viejas
        stale = [k for k, t in self._recent_messages.items() if now - t > self._dedup_window]
        for k in stale:
            del self._recent_messages[k]
        if msg_hash in self._recent_messages:
            StructuredLogRecord.warning(
                "duplicate_message_blocked",
                message=f"Mensaje duplicado ignorado (hash={msg_hash})",
                session_id=None,
                original_time=self._recent_messages[msg_hash],
            )
            return self._error_result(
                "Mensaje duplicado ignorado (ya se esta procesando esta solicitud).",
            )
        self._recent_messages[msg_hash] = now

        StructuredLogRecord.info(
            "process_message_start",
            message="Procesando mensaje",
            session_id=None,
            message_len=len(message) if message else 0,
            force_agent=force_agent or "",
        )

        # --- 1. Determine if this is a continuation or new task ---
        active_session = self._session_ctx.get_active()

        if self._is_continuation(message, active_session):
            StructuredLogRecord.info(
                "process_continuation",
                message="Continuando sesión activa",
                session_id=active_session.session_id if active_session else None,
            )
            result = self._handle_continuation(
                message, active_session, force_agent
            )

            # Self-healing: record progress
            if active_session:
                self._get_or_create_healing(active_session.session_id).record_progress()

            return result

        # --- 2. New task — decompose into plan ---
        plan = self._planner.decompose(message)
        session = self._session_ctx.get_or_create(message, plan)

        # Initialize self-healing context for this session
        healing = self._get_or_create_healing(session.session_id)
        healing.advance_level(1)

        level_count = len(plan.get_levels())
        StructuredLogRecord.info(
            "plan_created",
            message=f"Plan creado con {len(plan.subtasks)} subtasks en {level_count} niveles",
            session_id=session.session_id,
            subtask_count=len(plan.subtasks),
            max_level=level_count,
        )

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
        Process a subtask completion with self-healing checks.

        Args:
            session_id: The session ID.
            subtask_id: The completed subtask ID.
            result: The result/artifact from the subtask.

        Returns:
            OrchestratorResult for the next execution step.
        """
        StructuredLogRecord.info(
            "process_completion",
            message=f"Completando subtask {subtask_id}",
            session_id=session_id,
            subtask_id=subtask_id,
        )

        session = self._session_ctx.get_session(session_id)
        if not session:
            StructuredLogRecord.warning(
                "session_not_found",
                message=f"Sesión {session_id} no encontrada",
                session_id=session_id,
            )
            return self._empty_result()

        # Self-healing: record progress
        healing = self._get_or_create_healing(session_id)
        healing.record_progress()

        # Check if subtask was already completed (idempotency)
        existing = next(
            (s for s in session.plan.subtasks if s.id == subtask_id and s.completed),
            None,
        )
        if existing:
            StructuredLogRecord.info(
                "subtask_already_completed",
                message=f"Subtask {subtask_id} ya estaba completada",
                session_id=session_id,
            )
            # Still advance — it's a no-op
        else:
            self._session_ctx.mark_subtask_done(session, subtask_id, result)
            # Notify agents
            self._broadcast_completion(session, subtask_id, result)

            # Record agent success in circuit breaker
            subtask = next(
                (s for s in session.plan.subtasks if s.id == subtask_id),
                None,
            )
            if subtask:
                agent_cb = healing.get_circuit_breaker(subtask.agent)
                agent_cb.record_success()

            # Confidence-gated early stopping: evaluate and skip validation if confident
            self._evaluate_confidence_and_check_early_stop(
                session, subtask_id, result,
            )

        # If complete, celebrate
        if session.plan.is_complete():
            StructuredLogRecord.info(
                "plan_complete",
                message="Plan completado exitosamente",
                session_id=session_id,
                total_subtasks=len(session.plan.subtasks),
            )
            self._broadcast_complete(session)
            self._global_cb.record_success()
            return self._build_result(
                session, session.original_message, None, is_new_plan=False,
            )

        # Advance level if needed
        next_level = session.plan.get_next_level()
        if next_level:
            current_level_num = session.plan.get_current_level_num()
            healing.advance_level(current_level_num)

        # Check self-healing conditions
        timeout_issue = healing.check_timeout()
        if timeout_issue:
            StructuredLogRecord.warning(
                "level_timeout",
                message=timeout_issue,
                session_id=session_id,
                **healing.to_dict(),
            )

        stall_issue = healing.check_stalled()
        if stall_issue:
            StructuredLogRecord.warning(
                "stall_detected",
                message=stall_issue,
                session_id=session_id,
                stall_warnings=healing.stalled_warnings,
                **healing.to_dict(),
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

        status = self._session_ctx.get_status(session)

        # Add self-healing info
        healing = self._healing_contexts.get(session.session_id)
        if healing:
            cb_status = {
                k: f"{v.state}({v.failure_count}/{v.failure_threshold})"
                for k, v in healing.circuit_breakers.items()
            }
            status += (
                f"\n🔋 Self-Healing: "
                f"Nivel {healing.current_level}, "
                f"Último progreso: {time.time() - healing.last_progress_time:.0f}s atrás"
            )
            if cb_status:
                status += f"\n   Circuit Breakers: {cb_status}"

        return status

    def get_healing_status(self, session_id: str) -> Optional[Dict]:
        """Obtiene el estado de self-healing de una sesión."""
        healing = self._healing_contexts.get(session_id)
        return healing.to_dict() if healing else None

    def run_debate(
        self,
        session_id: str,
        task: str,
        agents: Optional[List[str]] = None,
        strategy: str = "consensus",
        dispatch_fn: Optional[callable] = None,
    ) -> "DebateResult":
        """
        Delegado a DebateRunner.

        Args:
            session_id: The session ID.
            task: The original task to debate.
            agents: List of agent names. If None, extracted from the plan.
            strategy: Debate strategy name ('consensus', 'critique', 'deliberation').
            dispatch_fn: Optional callable for obtaining agent responses.

        Returns:
            A DebateResult with the debate outcome.
        """
        from harness.orchestrator.debate_runner import DebateRunner

        runner = DebateRunner(self._store, self._session_ctx, self._bus)
        return runner.run_debate(session_id, task, agents, strategy, dispatch_fn)

    # ------------------------------------------------------------------
    # Confidence-gated early stopping
    # ------------------------------------------------------------------

    def _evaluate_confidence_and_check_early_stop(
        self,
        session: SessionState,
        subtask_id: str,
        result: str,
    ) -> Optional[ConfidenceScore]:
        """
        Evaluate confidence of a completed subtask and decide on early stopping.

        If the result has HIGH confidence AND all completed subtasks at the
        current execution level also have HIGH confidence, AND the next level
        is a validation/review level, skip that level entirely.

        Args:
            session: The current session state.
            subtask_id: The completed subtask ID.
            result: The subtask result text.

        Returns:
            ConfidenceScore if evaluated, None if evaluation was skipped.
        """
        # Find the subtask
        subtask = next(
            (s for s in session.plan.subtasks if s.id == subtask_id),
            None,
        )
        if not subtask:
            return None

        # Score this completion
        confidence = self._confidence_scorer.score_completion(
            task=subtask.description,
            result=result,
            agent=subtask.agent,
        )

        # Log the confidence score
        StructuredLogRecord.info(
            "confidence_score",
            message=f"Confianza para {subtask_id}: {confidence.score:.2f} ({confidence.level})",
            session_id=session.session_id,
            subtask_id=subtask_id,
            agent=subtask.agent,
            confidence_score=round(confidence.score, 4),
            confidence_level=confidence.level,
            confidence_signals=confidence.signals,
            should_stop=confidence.should_stop,
        )

        # Only proceed with early-stop check if confidence is HIGH
        if not confidence.should_stop:
            return confidence

        # Check if ALL completed subtasks in the current level have HIGH confidence
        levels = session.plan.get_levels()
        current_level_num = session.plan.get_current_level_num()

        if current_level_num >= len(levels):
            return confidence

        current_level = levels[current_level_num]
        completed_ids = {s.id for s in session.plan.subtasks if s.completed}

        # All subtasks in this level must be completed
        level_subtask_ids = {s.id for s in current_level}
        if not level_subtask_ids.issubset(completed_ids):
            # Not all done yet — can't early-stop a level that's still running
            return confidence

        # Check if next level exists and is a validation level
        next_level_num = current_level_num + 1
        if next_level_num >= len(levels):
            return confidence

        next_level = levels[next_level_num]
        next_confidence_impacts = {s.confidence_impact for s in next_level}

        # Only skip if ALL subtasks in the next level are "validation"
        # (i.e., review, verification, checking — not core work)
        if next_confidence_impacts == {"validation"} or (
            next_confidence_impacts == {"validation", "neutral"}
        ):
            # Skip the validation level — mark as completed with a note
            next_subtask_ids = []
            for st in next_level:
                next_subtask_ids.append(st.id)
                self._session_ctx.mark_subtask_done(
                    session,
                    st.id,
                    result=(
                        f"[SKIPPED by confidence-gated early stopping] "
                        f"Confidence score: {confidence.score:.2f} ({confidence.level}). "
                        f"Validation not required."
                    ),
                )
                StructuredLogRecord.info(
                    "early_stop_skip",
                    message=(
                        f"Subtask {st.id} omitida por early stopping "
                        f"(confianza={confidence.score:.2f})"
                    ),
                    session_id=session.session_id,
                    subtask_id=st.id,
                    agent=st.agent,
                    description=st.description,
                    confidence_score=round(confidence.score, 4),
                )

            StructuredLogRecord.info(
                "early_stop_triggered",
                message=(
                    f"Nivel de validación {next_level_num} omitido "
                    f"por alta confianza ({confidence.score:.2f})"
                ),
                session_id=session.session_id,
                current_level=current_level_num,
                skipped_level=next_level_num,
                skipped_subtasks=next_subtask_ids,
                confidence_score=round(confidence.score, 4),
            )

        return confidence

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

    def _get_or_create_healing(self, session_id: str) -> SelfHealingContext:
        """Obtiene o crea un contexto de self-healing para una sesión."""
        if session_id not in self._healing_contexts:
            self._healing_contexts[session_id] = SelfHealingContext(
                session_id=session_id,
                level_timeout_sec=self._level_timeout_sec,
                stall_timeout_sec=self._stall_timeout_sec,
            )
        return self._healing_contexts[session_id]

    def _error_result(self, message: str) -> OrchestratorResult:
        """Return an error result with a descriptive message."""
        plan = TaskPlan(session_id="error", original_message="")
        return OrchestratorResult(
            session_id="error",
            target_agent="coordinator",
            plan=plan,
            current_level=[],
            previous_results=[],
            session_status=f"❌ Error: {message}",
            communication_log=[],
            original_message="",
            is_new_plan=False,
            is_complete=False,
        )

    def _handle_continuation(
        self,
        message: str,
        session: SessionState,
        force_agent: Optional[str],
    ) -> OrchestratorResult:
        """Handle a continuation message (user wants to proceed)."""
        self._session_ctx.add_message(session, "user", message)

        StructuredLogRecord.info(
            "handle_continuation",
            message=f"Continuando sesión {session.session_id}",
            session_id=session.session_id,
            completed_subtasks=sum(1 for s in session.plan.subtasks if s.completed),
        )

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

        # --- Detect debate template ---
        is_debate = plan.template_name == "debate"
        debate_agents = []
        debate_strategy = ""
        if is_debate:
            # Extract unique non-coordinator agents from the plan for the debate
            debate_agents = sorted({
                st.agent for st in plan.subtasks
                if st.agent != "coordinator" and not st.completed
            })
            # Default to CONSENSUS strategy; can be overridden via metadata
            debate_strategy = "consensus"

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
            is_debate=is_debate,
            debate_agents=debate_agents,
            debate_strategy=debate_strategy,
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
        """Broadcast the new plan to all involved agents.

        CADA agente recibe SOLO su subtask especifica — no el mensaje generico.
        Esto previene que 3+ agentes ejecuten la misma tarea.
        """
        try:
            # Get next level (subtasks ready NOW) and all agents
            next_level = session.plan.get_next_level()
            agents = set()
            agent_subtasks: Dict[str, List[Dict]] = {}
            for st in session.plan.subtasks:
                agent_key = f"@{st.agent}"
                agents.add(agent_key)
                if agent_key not in agent_subtasks:
                    agent_subtasks[agent_key] = []
                agent_subtasks[agent_key].append({
                    "id": st.id,
                    "description": st.description,
                    "expected_output": st.expected_output,
                    "level": session.plan.get_current_level_num(),
                    "is_ready": st.id in {s.id for s in next_level},
                })

            summary = session.plan.get_summary()

            # Post plan summary to session channel (solo notificacion)
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

            # Notify CADA agente SOLO con su subtask especifica
            for agent in sorted(agents):
                subtasks = agent_subtasks.get(agent, [])
                ready_subtasks = [s for s in subtasks if s["is_ready"]]
                pending_subtasks = [s for s in subtasks if not s["is_ready"]]

                if ready_subtasks:
                    # Tiene trabajo AHORA — enviar request con subtask especifica
                    task_desc = ready_subtasks[0]["description"]
                    task_output = ready_subtasks[0]["expected_output"]
                    st_id = ready_subtasks[0]["id"]
                    self._bus.post_message(
                        channel=f"#session-{session.session_id}",
                        from_agent="@coordinator",
                        to_agent=agent,
                        message=(
                            f"🎯 TU TAREA: {task_desc}\n"
                            f"Output esperado: {task_output}\n"
                            f"SubtaskID: {st_id}\n"
                            f"Plan: {session.session_id}"
                        ),
                        message_type="request",
                    )
                else:
                    # No tiene trabajo ahora — solo notificar
                    self._bus.post_message(
                        channel=f"#session-{session.session_id}",
                        from_agent="@coordinator",
                        to_agent=agent,
                        message=(
                            f"⏳ Asignado al plan `{session.session_id}`.\n"
                            f"Esperarás turno cuando tus dependencias estén listas."
                            + (f"\nTareas pendientes: {len(pending_subtasks)}" if pending_subtasks else "")
                        ),
                        message_type="notification",
                    )

            StructuredLogRecord.info(
                "broadcast_plan",
                message=f"Plan broadcast a {len(agents)} agentes con subtasks individuales",
                session_id=session.session_id,
                agents=list(agents),
                subtask_count=len(session.plan.subtasks),
                next_level_count=len(next_level),
            )
        except Exception as exc:
            StructuredLogRecord.error(
                "broadcast_plan_error",
                message=str(exc),
                session_id=session.session_id,
            )

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
            StructuredLogRecord.warning(
                "broadcast_completion_error",
                message=str(exc),
                session_id=session.session_id,
                subtask_id=subtask_id,
            )

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
            StructuredLogRecord.warning(
                "broadcast_complete_error",
                message=str(exc),
                session_id=session.session_id,
            )

    def _empty_result(self) -> OrchestratorResult:
        """Return an empty result (error case)."""
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


# ---------------------------------------------------------------------------
# Configuracion de ShapedCache para TaskOrchestrator
# ---------------------------------------------------------------------------


def enable_cache(orchestrator: "TaskOrchestrator", max_tokens: int = 50000) -> None:
    """
    Habilitar ShapedCache en un TaskOrchestrator existente.

    Permite que el orquestador cachee respuestas semanticamente similares
    y las reutilice sin llamar al LLM, ahorrando tokens (ADR-0018).

    Args:
        orchestrator: Instancia de TaskOrchestrator.
        max_tokens: Maximo de tokens acumulados en el cache antes de
                    hacer LRU eviction. Por defecto 50000.

    Example:
        >>> from harness.orchestrator.task_orchestrator import enable_cache
        >>> orch = TaskOrchestrator()
        >>> enable_cache(orch, max_tokens=100000)
        >>> orch._shaped_cache is not None
        True
    """
    from harness.memory_rag.semantic_cache import SemanticCache, ShapedCache
    sem_cache = SemanticCache()
    orchestrator._shaped_cache = ShapedCache(
        semantic_cache=sem_cache,
        max_tokens=max_tokens,
    )
    stats = orchestrator._shaped_cache.get_stats()
    StructuredLogRecord.info(
        "cache_enabled",
        message=f"ShapedCache activado: max_tokens={max_tokens}",
        session_id="",
        **stats,
    )
