"""
Task Orchestrator — Plan-and-Execute with DAG parallelism (Async).

Version asincrona completa (ADR-0017: 4.8x speedup via asyncio).

Flow for ANY user message:
  1. RECEIVE: User sends message (with or without @agent)
  2. PLAN: TaskPlanner decomposes into DAG of subtasks
  3. TRACK: SessionContext preserves state
  4. COMMUNICATE: AgentBus notifies all relevant agents
  5. DISPATCH: For each ready subtask, prepare context with plan overview,
     previous subtask results, current subtask instructions, agent skill context
  6. EXECUTE: LLM receives the full structured context and produces results
  7. VERIFY: Coordinator checks completion, updates session, repeats

Key design decisions:
  - Parallel: subtasks at same level execute SIMULTANEOUSLY via asyncio.gather
  - Sequential: subtasks with dependencies wait for predecessors
  - Communication: results broadcast to all agents via AgentBus
  - Never lost: full session state persisted to LanceDB

Self-Healing features:
  - Circuit Breaker: open after N consecutive failures, auto-recover after timeout
  - Timeout Detection: per-level timeout kills stale execution
  - Progress Stall Detection: warns if no progress in N seconds
  - Structured Logging: all logs as JSON for centralized monitoring
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import logging
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar

from harness.orchestrator.agent_bus import AgentBus
from harness.orchestrator.confidence_scorer import ConfidenceScore, ConfidenceScorer
from harness.orchestrator.debate_orchestrator import (
    DebateOrchestrator,
    DebateResult,
    DebateStrategy,
)
from harness.orchestrator.session_context import SessionContext, SessionState
from harness.orchestrator.task_planner import TaskPlan, TaskPlanner
from harness.orchestrator.orchestration_result import OrchestratorResult
from harness.orchestrator.self_healing import CircuitBreaker, SelfHealingContext
from harness.orchestrator.structured_log import StructuredLogRecord

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# Decorador: async retry con backoff exponencial
# ---------------------------------------------------------------------------


def async_retry(
    max_retries: int = 3,
    backoff: float = 1.0,
    exceptions: tuple = (Exception,),
) -> Callable[[F], F]:
    """Reintenta operaciones async con backoff exponencial."""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[Exception] = None
            for attempt in range(1 + max_retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        wait = backoff * (2 ** attempt)
                        StructuredLogRecord.warning(
                            "async_retry",
                            message=f"Reintentando {func.__name__} "
                                    f"(intento {attempt+1}/{max_retries+1}): {exc}",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay_sec=round(wait, 2),
                        )
                        await asyncio.sleep(wait)
            raise AssertionError("Unreachable") from last_exc
        return wrapper  # type: ignore[return-value]
    return decorator


# ---------------------------------------------------------------------------
# TaskOrchestrator (async)
# ---------------------------------------------------------------------------


class TaskOrchestrator:
    """
    Orchestrates multi-agent task execution with Plan-and-Execute (async).

    Incorpora self-healing: circuit breaker, timeouts, stall detection,
    y logging estructurado como JSON. Toda operacion I/O-bound se ejecuta
    via asyncio para lograr el 4.8x speedup (ADR-0017).

    Compatibilidad sincrona via __call__:
        orch = TaskOrchestrator()
        result = orch("mi mensaje")   # sync
        result = await orch.process_message("mi mensaje")  # async
    """

    def __init__(
        self,
        vector_store: Optional[Any] = None,
        max_retries: int = 3,
        level_timeout_sec: float = 300.0,
        stall_timeout_sec: float = 120.0,
        verbose: bool = False,
    ) -> None:
        self._store = vector_store
        self._planner = TaskPlanner()
        self._session_ctx = SessionContext(vector_store)
        self._bus = AgentBus(vector_store=vector_store)
        self._max_retries = max_retries
        self._level_timeout_sec = level_timeout_sec
        self._stall_timeout_sec = stall_timeout_sec
        self._verbose = verbose
        self._confidence_scorer = ConfidenceScorer()
        self._healing_contexts: Dict[str, SelfHealingContext] = {}
        self._global_cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)
        self._shaped_cache = None
        self._recent_messages: Dict[str, float] = {}
        self._dedup_window: float = 30.0
        self._wal: Optional[Any] = None

        StructuredLogRecord.info(
            "orchestrator_init_async",
            message="TaskOrchestrator async inicializado",
            max_retries=max_retries, level_timeout_sec=level_timeout_sec,
            stall_timeout_sec=stall_timeout_sec, verbose=verbose,
        )

    # ------------------------------------------------------------------
    # Sync-compatibility wrapper
    # ------------------------------------------------------------------

    def __call__(self, message: str, force_agent: Optional[str] = None) -> OrchestratorResult:
        """Wrapper sincrono: ejecuta process_message en loop activo o nuevo."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.process_message(message, force_agent=force_agent), loop,
            )
            return future.result(timeout=self._level_timeout_sec + 30.0)
        return asyncio.run(self.process_message(message, force_agent=force_agent))

    # ------------------------------------------------------------------
    # Public API (async)
    # ------------------------------------------------------------------

    async def process_message(
        self,
        message: str,
        force_agent: Optional[str] = None,
    ) -> OrchestratorResult:
        """Procesa un mensaje a traves del pipeline completo de orquestacion.

        Args:
            message: The user's message.
            force_agent: Optional forced agent (if user used @agent).

        Returns:
            OrchestratorResult with plan, context, and execution state.
        """
        if not self._global_cb.is_available:
            StructuredLogRecord.warning(
                "global_circuit_open", message="Circuito global abierto",
                failures=self._global_cb.failure_count,
            )
            return self._error("Sistema en recuperación. Intenta de nuevo en unos segundos.")

        await self._ensure_wal()
        if self._wal is not None:
            self._wal.begin(
                operation_type="process_message",
                payload={"message": message[:100], "force_agent": force_agent},
            )

        cached = await self._check_cache(message)
        if cached is not None:
            return cached

        dup = self._dedup(message)
        if dup is not None:
            return dup

        StructuredLogRecord.info(
            "process_message_start", message="Procesando mensaje",
            session_id=None, message_len=len(message or ""), force_agent=force_agent or "",
        )

        active_session = self._session_ctx.get_active()
        if self._is_continuation(message, active_session):
            StructuredLogRecord.info(
                "process_continuation", message="Continuando sesion activa",
                session_id=active_session.session_id if active_session else None,
            )
            result = self._handle_continuation(message, active_session, force_agent)
            if active_session:
                self._get_healing(active_session.session_id).record_progress()
            return result

        plan = self._planner.decompose(message)
        session = self._session_ctx.get_or_create(message, plan)
        healing = self._get_healing(session.session_id)
        healing.advance_level(1)

        StructuredLogRecord.info(
            "plan_created",
            message=f"Plan creado con {len(plan.subtasks)} subtasks en {len(plan.get_levels())} niveles",
            session_id=session.session_id, subtask_count=len(plan.subtasks),
        )

        await self._broadcast_plan_async(session)
        return self._build_result(session, message, force_agent, is_new_plan=True)

    async def process_completion(
        self, session_id: str, subtask_id: str, result: str,
    ) -> OrchestratorResult:
        """Procesa la finalización de una subtask con self-healing (async).

        Args:
            session_id: The session ID.
            subtask_id: The completed subtask ID.
            result: The result/artifact from the subtask.

        Returns:
            OrchestratorResult for the next execution step.
        """
        StructuredLogRecord.info(
            "process_completion", message=f"Completando subtask {subtask_id}",
            session_id=session_id, subtask_id=subtask_id,
        )
        session = self._session_ctx.get_session(session_id)
        if not session:
            StructuredLogRecord.warning(
                "session_not_found", message=f"Sesión {session_id} no encontrada",
                session_id=session_id,
            )
            return self._error("Sesión no encontrada")

        healing = self._get_healing(session_id)
        healing.record_progress()

        existing = next(
            (s for s in session.plan.subtasks if s.id == subtask_id and s.completed), None,
        )
        if not existing:
            self._session_ctx.mark_subtask_done(session, subtask_id, result)
            await self._broadcast_completion_async(session, subtask_id, result)
            subtask = next((s for s in session.plan.subtasks if s.id == subtask_id), None)
            if subtask:
                self._get_healing(session_id).get_circuit_breaker(subtask.agent).record_success()
            self._evaluate_confidence_and_check_early_stop(session, subtask_id, result)

        if session.plan.is_complete():
            StructuredLogRecord.info(
                "plan_complete", message="Plan completado exitosamente",
                session_id=session_id, total_subtasks=len(session.plan.subtasks),
            )
            await self._broadcast_complete_async(session)
            self._global_cb.record_success()
            return self._build_result(session, session.original_message, None, is_new_plan=False)

        next_level = session.plan.get_next_level()
        if next_level:
            healing.advance_level(session.plan.get_current_level_num())

        timeout_issue = healing.check_timeout()
        if timeout_issue:
            StructuredLogRecord.warning("level_timeout", message=timeout_issue, **healing.to_dict())
        stall_issue = healing.check_stalled()
        if stall_issue:
            StructuredLogRecord.warning("stall_detected", message=stall_issue, **healing.to_dict())

        return self._build_result(session, session.original_message, None, is_new_plan=False)

    async def get_summary(self, session_id: Optional[str] = None) -> str:
        """Resumen legible del progreso de la sesion (async)."""
        session = self._session_ctx.get_session(session_id) if session_id else self._session_ctx.get_active()
        if not session:
            return "No hay sesiones activas."
        status = self._session_ctx.get_status(session)
        healing = self._healing_contexts.get(session.session_id)
        if healing:
            cb_status = {
                k: f"{v.state}({v.failure_count}/{v.failure_threshold})"
                for k, v in healing.circuit_breakers.items()
            }
            status += (
                f" | Self-Healing: Nivel {healing.current_level}, "
                f"Ultimo progreso: {time.time() - healing.last_progress_time:.0f}s atras"
            )
            if cb_status:
                status += f" | CB: {cb_status}"
        return status

    async def get_healing_status(self, session_id: str) -> Optional[Dict]:
        """Estado de self-healing de una sesion (async)."""
        healing = self._healing_contexts.get(session_id)
        return healing.to_dict() if healing else None

    async def run_debate(
        self, session_id: str, task: str,
        agents: Optional[List[str]] = None, strategy: str = "consensus",
        dispatch_fn: Optional[Callable[..., Any]] = None,
    ) -> "DebateResult":
        """Ejecuta debate multi-agente delegando en DebateRunner (async)."""
        from harness.orchestrator.debate_runner import DebateRunner
        runner = DebateRunner(self._store, self._session_ctx, self._bus)
        return await asyncio.to_thread(
            runner.run_debate, session_id, task, agents, strategy, dispatch_fn,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_wal(self) -> None:
        if self._wal is None:
            from harness.orchestrator.write_ahead_log import WriteAheadLog
            self._wal = WriteAheadLog()

    async def _check_cache(self, message: str) -> Optional[OrchestratorResult]:
        """Verifica ShapedCache de forma asincrona."""
        if self._shaped_cache is None:
            return None
        cached = await asyncio.to_thread(self._shaped_cache.get_shaped, message, 0.88)
        if cached is not None and cached.get("response"):
            StructuredLogRecord.info("cache_hit", message=f"Cache hit: {message[:50]}...", session_id="")
            return OrchestratorResult(
                session_id="", target_agent="coordinator", plan=None,  # type: ignore
                current_level=[], session_status="completed", previous_results=[],
                communication_log=[], original_message=message, is_new_plan=False, is_complete=True,
            )
        StructuredLogRecord.info("cache_miss", message=f"Cache miss: {message[:50]}...", session_id="")
        try:
            hr = float(self._shaped_cache.hit_rate)
            ct = float(getattr(self._shaped_cache, '_threshold', 0.88))
            if hr > 0.9:
                self._shaped_cache._threshold = max(0.80, ct - 0.02)
            elif hr < 0.5:
                self._shaped_cache._threshold = min(0.95, ct + 0.02)
        except (TypeError, ValueError, AttributeError):
            pass
        return None

    def _dedup(self, message: str) -> Optional[OrchestratorResult]:
        """Idempotencia: evita duplicados del mismo mensaje."""
        msg_hash = hashlib.sha256((message or "").encode()).hexdigest()[:16]
        now = time.time()
        stale = [k for k, t in self._recent_messages.items() if now - t > self._dedup_window]
        for k in stale:
            del self._recent_messages[k]
        if msg_hash in self._recent_messages:
            StructuredLogRecord.warning(
                "duplicate_blocked", message=f"Duplicado ignorado (hash={msg_hash})", session_id=None,
            )
            return self._error("Mensaje duplicado ignorado.")
        self._recent_messages[msg_hash] = now
        return None

    def _is_continuation(self, message: str, session: Optional[SessionState]) -> bool:
        """Determina si el mensaje es continuacion de trabajo previo."""
        if not session or session.completed:
            return False
        msg_lower = message.lower()
        keywords = ["continuar","continue","siguiente","next","sigue","proceder","proceed",
                     "avanzar","adelante","terminar","finish","completar","complete","paso","step","sigue con"]
        if any(kw in msg_lower for kw in keywords):
            return True
        if len(message.strip()) < 10:
            return True
        return False

    def _get_healing(self, session_id: str) -> SelfHealingContext:
        if session_id not in self._healing_contexts:
            self._healing_contexts[session_id] = SelfHealingContext(
                session_id=session_id, level_timeout_sec=self._level_timeout_sec,
                stall_timeout_sec=self._stall_timeout_sec,
            )
        return self._healing_contexts[session_id]

    def _handle_continuation(self, message: str, session: SessionState, force_agent: Optional[str]) -> OrchestratorResult:
        self._session_ctx.add_message(session, "user", message)
        return self._build_result(session, message, force_agent, is_new_plan=False)

    def _build_result(self, session: SessionState, message: str, force_agent: Optional[str], is_new_plan: bool) -> OrchestratorResult:
        plan = session.plan
        next_level = plan.get_next_level()
        target_agent = force_agent or self._resolve_target_agent(next_level)
        current_level = [{
            "id": st.id, "agent": st.agent, "description": st.description,
            "expected_output": st.expected_output, "context_hint": st.context_hint,
            "dependencies": st.dependencies,
        } for st in next_level]
        previous_results = [{
            "id": st.id, "agent": st.agent, "description": st.description, "result": st.result,
        } for st in plan.subtasks if st.completed and st.result]
        comm_log = self._bus.get_channel_history(f"#session-{session.session_id}", limit=20)
        status = self._session_ctx.get_status(session)
        is_debate = plan.template_name == "debate"
        debate_agents = sorted({st.agent for st in plan.subtasks if st.agent != "coordinator" and not st.completed}) if is_debate else []
        return OrchestratorResult(
            session_id=session.session_id, target_agent=target_agent, plan=plan,
            current_level=current_level, previous_results=previous_results,
            session_status=status, communication_log=comm_log, original_message=message,
            is_new_plan=is_new_plan, is_complete=plan.is_complete(),
            is_debate=is_debate, debate_agents=debate_agents, debate_strategy="consensus" if is_debate else "",
        )

    def _resolve_target_agent(self, next_level: List) -> str:
        if not next_level:
            return "coordinator"
        agents = {st.agent for st in next_level}
        return agents.pop() if len(agents) == 1 else "coordinator"

    def _evaluate_confidence_and_check_early_stop(self, session: SessionState, subtask_id: str, result: str) -> Optional[ConfidenceScore]:
        """Evalua confianza y decide early stopping del nivel de validacion."""
        subtask = next((s for s in session.plan.subtasks if s.id == subtask_id), None)
        if not subtask:
            return None
        confidence = self._confidence_scorer.score_completion(task=subtask.description, result=result, agent=subtask.agent)
        StructuredLogRecord.info(
            "confidence_score", message=f"Confianza {subtask_id}: {confidence.score:.2f} ({confidence.level})",
            session_id=session.session_id, score=round(confidence.score, 4), level=confidence.level,
            signals=confidence.signals, should_stop=confidence.should_stop,
        )
        if not confidence.should_stop:
            return confidence
        levels = session.plan.get_levels()
        current_level_num = session.plan.get_current_level_num()
        if current_level_num >= len(levels):
            return confidence
        level_ids = {s.id for s in levels[current_level_num]}
        completed = {s.id for s in session.plan.subtasks if s.completed}
        if not level_ids.issubset(completed):
            return confidence
        next_num = current_level_num + 1
        if next_num >= len(levels):
            return confidence
        next_impacts = {s.confidence_impact for s in levels[next_num]}
        if next_impacts in ({"validation"}, {"validation", "neutral"}):
            for st in levels[next_num]:
                self._session_ctx.mark_subtask_done(
                    session, st.id,
                    result=f"[SKIPPED by confidence-gated early stopping] Score: {confidence.score:.2f} ({confidence.level}).",
                )
                StructuredLogRecord.info(
                    "early_stop_skip", message=f"Subtask {st.id} omitida (confianza={confidence.score:.2f})",
                    session_id=session.session_id, subtask_id=st.id, agent=st.agent,
                )
        return confidence

    # ------------------------------------------------------------------
    # Async broadcasts (parallel via asyncio.gather)
    # ------------------------------------------------------------------

    async def _broadcast_plan_async(self, session: SessionState) -> None:
        """Broadcast plan a todos los agentes en paralelo via asyncio.gather."""
        try:
            next_level = session.plan.get_next_level()
            agents: set = set()
            agent_subtasks: Dict[str, List[Dict]] = {}
            for st in session.plan.subtasks:
                ak = f"@{st.agent}"
                agents.add(ak)
                agent_subtasks.setdefault(ak, []).append({
                    "id": st.id, "description": st.description,
                    "expected_output": st.expected_output,
                    "level": session.plan.get_current_level_num(),
                    "is_ready": st.id in {s.id for s in next_level},
                })
            summary = session.plan.get_summary()
            tasks = [
                asyncio.to_thread(
                    self._bus.post_message, f"#session-{session.session_id}",
                    "@coordinator", "@all",
                    f"📋 **NUEVO PLAN**\n\nTarea: {session.original_message[:120]}\n"
                    f"Agentes: {', '.join(sorted(agents))}\n\n{summary}",
                    "notification",
                ),
            ]
            for agent in sorted(agents):
                subs = agent_subtasks.get(agent, [])
                ready = [s for s in subs if s["is_ready"]]
                pending = [s for s in subs if not s["is_ready"]]
                if ready:
                    tasks.append(asyncio.to_thread(
                        self._bus.post_message, f"#session-{session.session_id}",
                        "@coordinator", agent,
                        f"🎯 TU TAREA: {ready[0]['description']}\nOutput: {ready[0]['expected_output']}\n"
                        f"SubtaskID: {ready[0]['id']}\nPlan: {session.session_id}",
                        "request",
                    ))
                else:
                    tasks.append(asyncio.to_thread(
                        self._bus.post_message, f"#session-{session.session_id}",
                        "@coordinator", agent,
                        f"⏳ Asignado al plan `{session.session_id}`. Esperaras turno."
                        + (f"\nPendientes: {len(pending)}" if pending else ""),
                        "notification",
                    ))
            await asyncio.gather(*tasks, return_exceptions=True)
            StructuredLogRecord.info(
                "broadcast_plan", message=f"Plan broadcast a {len(agents)} agentes (async)",
                session_id=session.session_id, agents=list(agents), next_level_count=len(next_level),
            )
        except Exception as exc:
            StructuredLogRecord.error("broadcast_plan_error", message=str(exc), session_id=session.session_id)

    async def _broadcast_completion_async(self, session: SessionState, subtask_id: str, result: str) -> None:
        """Broadcast completado de subtask a agentes en paralelo."""
        try:
            subtask = next((s for s in session.plan.subtasks if s.id == subtask_id), None)
            if not subtask:
                return
            tasks = [
                asyncio.to_thread(
                    self._bus.post_message, f"#session-{session.session_id}",
                    f"@{subtask.agent}", "@all",
                    f"✅ **Subtask {subtask_id} COMPLETADA**\nAgente: @{subtask.agent}\n"
                    f"Que: {subtask.description}\nResultado: {result[:200]}",
                    "response",
                ),
            ]
            waiting = [s for s in session.plan.subtasks if not s.completed and subtask_id in s.dependencies]
            for st in waiting:
                tasks.append(asyncio.to_thread(
                    self._bus.post_message, f"#session-{session.session_id}",
                    "@coordinator", f"@{st.agent}",
                    f"Tu dependencia `{subtask_id}` ha sido completada. Ahora puedes comenzar: **{st.description}**",
                    "notification",
                ))
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as exc:
            StructuredLogRecord.warning("broadcast_completion_error", message=str(exc), session_id=session.session_id)

    async def _broadcast_complete_async(self, session: SessionState) -> None:
        """Broadcast de plan completo."""
        try:
            summary = "\n".join(
                f"{'✅' if st.completed else '❌'} [{st.agent}] {st.description}"
                for st in session.plan.subtasks
            )
            await asyncio.to_thread(
                self._bus.post_message, f"#session-{session.session_id}",
                "@coordinator", "@all",
                f"🎉 **PLAN COMPLETO**\n\nSesión: {session.session_id}\n"
                f"Tarea: {session.original_message[:120]}\n\n{summary}",
                "notification",
            )
        except Exception as exc:
            StructuredLogRecord.warning("broadcast_complete_error", message=str(exc), session_id=session.session_id)

    def _error(self, message: str) -> OrchestratorResult:
        plan = TaskPlan(session_id="error", original_message="")
        return OrchestratorResult(
            session_id="error", target_agent="coordinator", plan=plan,
            current_level=[], previous_results=[], session_status=f"Error: {message}",
            communication_log=[], original_message="", is_new_plan=False, is_complete=False,
        )


# ---------------------------------------------------------------------------
# ShapedCache helper
# ---------------------------------------------------------------------------


def enable_cache(orchestrator: TaskOrchestrator, max_tokens: int = 50000) -> None:
    """Habilitar ShapedCache en TaskOrchestrator (ADR-0018 Token Economics)."""
    from harness.memory_rag.semantic_cache import SemanticCache, ShapedCache
    orchestrator._shaped_cache = ShapedCache(semantic_cache=SemanticCache(), max_tokens=max_tokens)
    StructuredLogRecord.info(
        "cache_enabled", message=f"ShapedCache activado: max_tokens={max_tokens}",
        session_id="", **(orchestrator._shaped_cache.get_stats()),
    )


# ---------------------------------------------------------------------------
# Helper sync runner
# ---------------------------------------------------------------------------


def run_process_message(orchestrator: TaskOrchestrator, message: str, force_agent: Optional[str] = None) -> OrchestratorResult:
    """Ejecutar process_message sincrono (wrapper asyncio.run)."""
    return asyncio.run(orchestrator.process_message(message, force_agent=force_agent))
