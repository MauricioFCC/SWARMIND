"""Tests for TaskOrchestrator — Plan-and-Execute orchestration."""

import pytest
from harness.orchestrator.task_orchestrator import TaskOrchestrator, OrchestratorResult


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
        assert result.plan.subtasks[0].agent == "builder"

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
        """Implementation task → target agent is builder."""
        result = self.orch.process_message("implementar API en Rust")
        assert result.target_agent == "builder"

    def test_target_agent_scientist(self):
        """Research task → target agent is scientist."""
        result = self.orch.process_message("investigar patrones")
        assert result.target_agent == "scientist"

    def test_target_agent_guardian(self):
        """Security task → target agent is guardian."""
        result = self.orch.process_message("auditar seguridad")
        assert result.target_agent == "guardian"

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
