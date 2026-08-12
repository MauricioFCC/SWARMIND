"""Mixin ``_BroadcastingMixin`` — broadcasts async y construcción de errores.

Extracción mecánica de los métodos de difusión de la clase ``TaskOrchestrator``
del módulo original ``harness/orchestrator/task_orchestrator.py`` (patrón de
mixins ya usado en ``harness/orchestrator/agent_bus/``; sin cambios de lógica
ni firmas).
"""

from __future__ import annotations

import asyncio

from harness.orchestrator.orchestration_result import OrchestratorResult
from harness.orchestrator.session_context import SessionState
from harness.orchestrator.structured_log import StructuredLogRecord
from harness.orchestrator.task_planner import TaskPlan


class _BroadcastingMixin:
    """Mixin con los métodos async de broadcast del orquestador.

    Requiere que la clase huésped exponga ``self._bus`` (AgentBus) y
    ``self._session_ctx`` (SessionContext), tal como los inicializa
    ``TaskOrchestrator.__init__``.
    """

    async def _broadcast_plan_async(self, session: SessionState) -> None:
        """Broadcast plan a todos los agentes en paralelo via asyncio.gather."""
        try:
            next_level = session.plan.get_next_level()
            agents: set = set()
            agent_subtasks: dict[str, list[dict]] = {}
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
                    f"ðŸ“‹ **NUEVO PLAN**\n\nTarea: {session.original_message[:120]}\n"
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
                        f"ðŸŽ¯ TU TAREA: {ready[0]['description']}\nOutput: {ready[0]['expected_output']}\n"
                        f"SubtaskID: {ready[0]['id']}\nPlan: {session.session_id}",
                        "request",
                    ))
                else:
                    tasks.append(asyncio.to_thread(
                        self._bus.post_message, f"#session-{session.session_id}",
                        "@coordinator", agent,
                        f"â³ Asignado al plan `{session.session_id}`. Esperaras turno."
                        + (f"\nPendientes: {len(pending)}" if pending else ""),
                        "notification",
                    ))
            await asyncio.gather(*tasks, return_exceptions=True)
            StructuredLogRecord.info(
                "broadcast_plan", message=f"Plan broadcast a {len(agents)} agentes (async)",
                session_id=session.session_id, agents=list(agents), next_level_count=len(next_level),
            )
        except Exception as exc:  # noqa: BLE001
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
                    f"âœ… **Subtask {subtask_id} COMPLETADA**\nAgente: @{subtask.agent}\n"
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
        except Exception as exc:  # noqa: BLE001
            StructuredLogRecord.warning("broadcast_completion_error", message=str(exc), session_id=session.session_id)

    async def _broadcast_complete_async(self, session: SessionState) -> None:
        """Broadcast de plan completo."""
        try:
            summary = "\n".join(
                f"{'âœ…' if st.completed else 'âŒ'} [{st.agent}] {st.description}"
                for st in session.plan.subtasks
            )
            await asyncio.to_thread(
                self._bus.post_message, f"#session-{session.session_id}",
                "@coordinator", "@all",
                f"ðŸŽ‰ **PLAN COMPLETO**\n\nSesiÃ³n: {session.session_id}\n"
                f"Tarea: {session.original_message[:120]}\n\n{summary}",
                "notification",
            )
        except Exception as exc:  # noqa: BLE001
            StructuredLogRecord.warning("broadcast_complete_error", message=str(exc), session_id=session.session_id)

    def _error(self, message: str) -> OrchestratorResult:
        plan = TaskPlan(session_id="error", original_message="")
        return OrchestratorResult(
            session_id="error", target_agent="coordinator", plan=plan,
            current_level=[], previous_results=[], session_status=f"Error: {message}",
            communication_log=[], original_message="", is_new_plan=False, is_complete=False,
        )
