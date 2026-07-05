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

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from harness.orchestrator.agent_bus import AgentBus
from harness.orchestrator.task_planner import TaskPlan, TaskPlanner
from harness.orchestrator.session_context import SessionContext, SessionState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured JSON Logging
# ---------------------------------------------------------------------------

class StructuredLogRecord:
    """
    Structured log record as JSON.

    Cada entrada incluye: timestamp, level, module, session_id (opcional),
    event, y detalles específicos.
    """

    def __init__(
        self,
        event: str,
        level: str = "INFO",
        session_id: Optional[str] = None,
        message: str = "",
        **extra,
    ) -> None:
        self._data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "module": "task_orchestrator",
            "event": event,
            "session_id": session_id or "",
            "message": message,
            **extra,
        }

    def log(self, logger_instance: logging.Logger) -> None:
        level_map = {
            "DEBUG": logger_instance.debug,
            "INFO": logger_instance.info,
            "WARNING": logger_instance.warning,
            "ERROR": logger_instance.error,
            "CRITICAL": logger_instance.critical,
        }
        level_map.get(self._data["level"], logger_instance.info)(
            "%s", json.dumps(self._data, ensure_ascii=False)
        )

    @staticmethod
    def info(event: str, message: str = "", session_id: Optional[str] = None, **extra):
        StructuredLogRecord(event, "INFO", session_id, message, **extra).log(logger)

    @staticmethod
    def warning(event: str, message: str = "", session_id: Optional[str] = None, **extra):
        StructuredLogRecord(event, "WARNING", session_id, message, **extra).log(logger)

    @staticmethod
    def error(event: str, message: str = "", session_id: Optional[str] = None, **extra):
        StructuredLogRecord(event, "ERROR", session_id, message, **extra).log(logger)

    @staticmethod
    def debug(event: str, message: str = "", session_id: Optional[str] = None, **extra):
        StructuredLogRecord(event, "DEBUG", session_id, message, **extra).log(logger)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

@dataclass
class CircuitBreaker:
    """
    Circuit Breaker pattern para operaciones sobre agentes.

    Estados:
      - closed:   operación normal, failures count
      - open:     umbral de fallos alcanzado, rechaza operaciones
      - half-open: periodo de recuperación, permite 1 intento

    Attributes:
        failure_threshold: N fallos consecutivos para abrir el circuito
        recovery_timeout:  segundos hasta pasar a half-open
        failure_count:     contador actual de fallos consecutivos
        state:             estado actual
        last_failure_time: timestamp del último fallo
    """
    failure_threshold: int = 3
    recovery_timeout: float = 30.0
    failure_count: int = 0
    state: str = "closed"
    last_failure_time: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_failure(self) -> None:
        """Registra un fallo. Abre el circuito si se excede el umbral."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                StructuredLogRecord.warning(
                    "circuit_breaker_open",
                    message=f"Circuit abierto tras {self.failure_count} fallos",
                    failure_count=self.failure_count,
                    threshold=self.failure_threshold,
                )

    def record_success(self) -> None:
        """Registra un éxito. Cierra/resetea el circuito."""
        with self._lock:
            self.failure_count = 0
            if self.state == "half-open":
                self.state = "closed"
                StructuredLogRecord.info(
                    "circuit_breaker_closed",
                    message="Circuit cerrado tras recuperación exitosa",
                )
            elif self.state == "open":
                self.state = "half-open"
                StructuredLogRecord.info(
                    "circuit_breaker_half_open",
                    message="Circuit en half-open, intentando recuperación",
                )

    @property
    def is_available(self) -> bool:
        """Checkea si el circuito permite ejecutar operaciones."""
        with self._lock:
            if self.state == "closed":
                return True
            if self.state == "open":
                # Check if recovery timeout has elapsed
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = "half-open"
                    StructuredLogRecord.info(
                        "circuit_breaker_half_open",
                        message="Circuit pasó a half-open por timeout",
                    )
                    return True
                return False
            # half-open: allow one attempt
            return True

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(state={self.state}, "
            f"failures={self.failure_count}/{self.failure_threshold})"
        )


# ---------------------------------------------------------------------------
# Self-Healing Context
# ---------------------------------------------------------------------------

@dataclass
class SelfHealingContext:
    """
    Contexto de self-healing para una sesión activa.

    Trackea:
      - Tiempo transcurrido por nivel (timeout detection)
      - Último progreso registrado (stall detection)
      - Circuit breaker por agente
    """
    session_id: str
    level_start_time: float = field(default_factory=time.time)
    last_progress_time: float = field(default_factory=time.time)
    current_level: int = 0
    level_timeout_sec: float = 300.0
    stall_timeout_sec: float = 120.0
    circuit_breakers: Dict[str, CircuitBreaker] = field(default_factory=dict)
    stalled_warnings: int = 0
    max_stalled_warnings: int = 3

    def get_circuit_breaker(self, agent: str) -> CircuitBreaker:
        """Obtiene (o crea) el circuit breaker para un agente."""
        if agent not in self.circuit_breakers:
            self.circuit_breakers[agent] = CircuitBreaker()
        return self.circuit_breakers[agent]

    def record_progress(self) -> None:
        """Registra que hubo progreso."""
        self.last_progress_time = time.time()

    def advance_level(self, level: int) -> None:
        """Avanza a un nuevo nivel."""
        self.current_level = level
        self.level_start_time = time.time()
        self.record_progress()

    def check_timeout(self) -> Optional[str]:
        """Checkea timeout del nivel actual."""
        elapsed = time.time() - self.level_start_time
        if elapsed > self.level_timeout_sec:
            return (
                f"LEVEL_TIMEOUT: Nivel {self.current_level} "
                f"excedió {self.level_timeout_sec}s ({elapsed:.0f}s transcurridos)"
            )
        return None

    def check_stalled(self) -> Optional[str]:
        """Checkea si el progreso está estancado."""
        elapsed = time.time() - self.last_progress_time
        if elapsed > self.stall_timeout_sec:
            self.stalled_warnings += 1
            return (
                f"STALL_DETECTED: Sin progreso por {elapsed:.0f}s "
                f"(umbral: {self.stall_timeout_sec}s, "
                f"advertencia {self.stalled_warnings}/{self.max_stalled_warnings})"
            )
        return None

    def is_critical(self) -> bool:
        """Determina si la sesión está en estado crítico."""
        return self.stalled_warnings >= self.max_stalled_warnings

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "level": self.current_level,
            "level_age_sec": round(time.time() - self.level_start_time, 1),
            "last_progress_sec": round(time.time() - self.last_progress_time, 1),
            "stalled_warnings": self.stalled_warnings,
            "circuit_breakers": {
                k: {"state": v.state, "failures": v.failure_count}
                for k, v in self.circuit_breakers.items()
            },
        }


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

        # Self-healing contexts por sesión
        self._healing_contexts: Dict[str, SelfHealingContext] = {}

        # Global circuit breaker para el orquestador mismo
        self._global_cb = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
        )

        StructuredLogRecord.info(
            "orchestrator_init",
            message=f"TaskOrchestrator inicializado",
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

        StructuredLogRecord.info(
            "process_message_start",
            message=f"Procesando mensaje",
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
        from harness.orchestrator.task_planner import TaskPlan
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

            StructuredLogRecord.info(
                "broadcast_plan",
                message=f"Plan broadcast a {len(agents)} agentes",
                session_id=session.session_id,
                agents=list(agents),
                subtask_count=len(session.plan.subtasks),
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
