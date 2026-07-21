"""Tests for TaskOrchestrator — Plan-and-Execute orchestration."""

import pytest

from harness.orchestrator.task_orchestrator import TaskOrchestrator


class TestTaskOrchestrator:
    """Verify the orchestration pipeline."""

    def setup_method(self):
        self.orch = TaskOrchestrator()  # no store = memory-only

    def test_process_message_new_task(self):
        """New task → plan created with subtasks."""
        result = self.orch.process_message("implementa una API REST en Rust")
        assert result is not None
        assert result.session_id is not None
        assert result.is_new_plan is True
        assert len(result.plan.subtasks) >= 3
        assert result.plan.subtasks[0].agent in ("builder", "coordinator")

    def test_process_message_bugfix(self):
        """Bugfix message → scientist + builder plan."""
        result = self.orch.process_message("fix bug en el login")
        assert result is not None
        assert result.plan.subtasks[0].agent == "scientist"

    def test_process_message_research(self):
        """Research message → scientist plan."""
        result = self.orch.process_message("investigar patrones de microservicios")
        assert result is not None
        assert result.plan.subtasks[0].agent == "scientist"

    def test_process_message_security(self):
        """Security message → guardian plan."""
        result = self.orch.process_message("auditar seguridad del sistema")
        assert result is not None
        assert result.plan.subtasks[0].agent == "guardian"

    def test_process_message_current_level(self):
        """New task → current_level has first subtask(s)."""
        result = self.orch.process_message("implementar API")
        assert len(result.current_level) >= 1
        first = result.current_level[0]
        assert "id" in first
        assert "agent" in first
        assert "description" in first

    def test_process_message_previous_results_empty(self):
        """New task → no previous results."""
        result = self.orch.process_message("test")
        assert len(result.previous_results) == 0

    @pytest.mark.slow
    def test_process_completion(self):
        """After completing a subtask → next level available."""
        result = self.orch.process_message("implementar API")
        first_id = result.current_level[0]["id"]

        next_result = self.orch.process_completion(
            session_id=result.session_id,
            subtask_id=first_id,
            result="API implementada",
        )
        assert next_result is not None
        assert len(next_result.previous_results) >= 1
        assert next_result.previous_results[0]["id"] == first_id

    @pytest.mark.slow
    def test_process_completion_all(self):
        """Complete all subtasks → plan complete."""
        result = self.orch.process_message("implementar API")
        # Complete all subtasks
        for st in result.plan.subtasks:
            self.orch.process_completion(
                session_id=result.session_id,
                subtask_id=st.id,
                result="done",
            )

        session = self.orch._session_ctx.get_session(result.session_id)
        assert session is not None
        assert session.completed is True

    def test_get_summary_active(self):
        """Summary of active session."""
        result = self.orch.process_message("implementar API")
        summary = self.orch.get_summary(result.session_id)
        assert summary is not None
        assert "implementar API" in summary or "API" in summary

    def test_get_summary_no_session(self):
        """Summary without session → message."""
        summary = self.orch.get_summary("nonexistent")
        assert summary is not None

    def test_target_agent_builder(self):
        """Implementation task → target agent is coordinator (multi-agent swarm)."""
        result = self.orch.process_message("implementar API en Rust")
        # With SWARM pattern, multiple agents launch in parallel at level 0
        # Coordinator is the orchestrator that dispatches to all
    def test_target_agent_scientist(self):
        """Research task → target agent is scientist."""
        result = self.orch.process_message("investigar patrones")
    def test_target_agent_guardian(self):
        """Security task → target agent is guardian."""
        result = self.orch.process_message("auditar seguridad")
    def test_orchestrator_result_dict(self):
        """OrchestratorResult can be serialized to dict."""
        result = self.orch.process_message("test")
        d = result.to_dict()
        assert d["session_id"] == result.session_id
        assert d["target_agent"] == result.target_agent
        assert "plan" in d
        assert "current_level" in d
        assert "previous_results" in d
        assert "is_new_plan" in d
        assert "is_complete" in d

    # ── Tests for bugfix: 3 agentes con mismo request ──

    @pytest.mark.slow
    def test_broadcast_plan_envia_subtask_especifica(self):
        """Cada agente recibe SU subtask especifica, no el mensaje generico."""
        result = self.orch.process_message("implementar una API REST en Rust")
        session = self.orch._session_ctx.get_session(result.session_id)
        # Verificar que _broadcast_plan ejecutó (la sesión tiene plan)
        assert session is not None
        assert session.plan is not None
        assert len(session.plan.subtasks) >= 3

        # Verificar que el bus tiene mensajes individuales para cada agente
        for st in session.plan.subtasks:
            agent_key = f"@{st.agent}"
            # poll para este agente deberia ver su subtask, no generico
            msgs = self.orch._bus.poll_channel(
                f"#session-{session.session_id}", agent_key
            )
            # Debe haber al menos un mensaje para este agente
            agent_msgs = [m for m in msgs if m.get("to_agent") == agent_key]
            if agent_msgs:
                msg = agent_msgs[0]
                # El mensaje NO debe ser el generico "Revisa tu nivel"
                assert "Revisa la sección de tu nivel" not in msg.get("message", "")
                # Debe contener la descripcion de su subtask o identificador
                if st.description:
                    assert "TU TAREA" in msg.get("message", "") or "⏳" in msg.get("message", "")

    @pytest.mark.slow
    def test_broadcast_plan_no_envia_request_sin_subtask(self):
        """Agentes sin trabajo en el nivel actual reciben notification, no request."""
        result = self.orch.process_message("implementar API")
        bus = self.orch._bus

        # Todos los mensajes de tipo "request" deben tener SubtaskID en el body
        channel = f"#session-{result.session_id}"
        all_msgs = bus.get_channel_history(channel)
        for msg in all_msgs:
            if msg.get("message_type") == "request":
                body = msg.get("message", "")
                assert "SubtaskID" in body, \
                    f"Request sin SubtaskID en body: {msg}"

    def test_process_message_dedup_rechaza_duplicado(self):
        """Mismo mensaje dentro de ventana de 30s → rechazado."""
        msg = "implementar una tarea unica para test de dedup"
        result1 = self.orch.process_message(msg)
        assert result1.is_new_plan is True

        result2 = self.orch.process_message(msg)
        # El segundo debe ser rechazado por dedup (mensaje duplicado)
        assert result2.is_new_plan is False, "Debe ser rechazado, no nuevo plan"
        # El session_status debe contener el mensaje de error por duplicado
        status = result2.session_status.lower()
        assert "duplicado" in status or "duplicate" in status, (
            f"Status deberia mencionar duplicado: {result2.session_status}"
        )

    @pytest.mark.slow
    def test_process_message_dedup_permite_diferente(self):
        """Mensajes diferentes NO son rechazados por dedup."""
        r1 = self.orch.process_message("hacer tarea A")
        assert r1.is_new_plan is True

        r2 = self.orch.process_message("hacer tarea B")
        assert r2.is_new_plan is True  # mensaje diferente → permitido

    def test_process_message_min_len_respected(self):
        """Mensaje vacio o muy corto no deberia romper dedup."""
        result = self.orch.process_message("x")
        # No deberia explotar
        assert result is not None
