"""Tests for SessionContext — session state persistence and tracking."""

import pytest
from harness.orchestrator.task_planner import SubTask, TaskPlan, TaskPlanner
from harness.orchestrator.session_context import SessionContext, SessionState


class TestSessionContext:
    """Verify session state management."""

    def setup_method(self):
        self.ctx = SessionContext()  # memory-only (no store)
        self.planner = TaskPlanner()

    def test_get_or_create_with_plan(self):
        """New plan → new session."""
        plan = self.planner.decompose("implementar API")
        session = self.ctx.get_or_create("implementar API", plan)
        assert session is not None
        assert session.session_id == plan.session_id
        assert session.original_message == "implementar API"

    def test_get_active_empty(self):
        """No sessions → None."""
        session = self.ctx.get_active()
        assert session is None

    def test_get_active_after_create(self):
        """After creating, get_active returns it."""
        plan = self.planner.decompose("test")
        session = self.ctx.get_or_create("test", plan)
        active = self.ctx.get_active()
        assert active is not None
        assert active.session_id == plan.session_id

    def test_mark_subtask_done(self):
        """Marking subtask done updates state."""
        plan = self.planner.decompose("implementar API")
        session = self.ctx.get_or_create("test", plan)

        subtask_id = plan.subtasks[0].id
        result = self.ctx.mark_subtask_done(session, subtask_id, "código listo")

        assert result is True
        # Verify subtask is marked
        for st in session.plan.subtasks:
            if st.id == subtask_id:
                assert st.completed is True
                assert st.result == "código listo"
                break

    def test_mark_subtask_done_unknown(self):
        """Unknown subtask ID → False."""
        plan = self.planner.decompose("test")
        session = self.ctx.get_or_create("test", plan)
        result = self.ctx.mark_subtask_done(session, "nonexistent", "result")
        assert result is False

    def test_session_complete(self):
        """Session marked complete when all subtasks done."""
        # Create a simple plan with 1 subtask
        subtasks = [
            SubTask(id="s1", agent="builder", description="code", dependencies=[]),
        ]
        plan = TaskPlan(session_id="test", original_message="simple", subtasks=subtasks)
        session = self.ctx.get_or_create("simple", plan)

        assert not session.completed
        self.ctx.mark_subtask_done(session, "s1", "done")
        assert session.completed is True

    def test_add_message(self):
        """Messages are tracked in session."""
        plan = self.planner.decompose("test")
        session = self.ctx.get_or_create("test", plan)
        assert len(session.messages) == 0

        self.ctx.add_message(session, "user", "hello")
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "hello"

    def test_get_status(self):
        """Status string is informative."""
        plan = self.planner.decompose("test")
        session = self.ctx.get_or_create("test", plan)
        status = self.ctx.get_status(session)
        assert "test" in status
        assert "Sesión" in status

    def test_get_status_after_completion(self):
        """Status shows completed items."""
        plan = self.planner.decompose("test")
        session = self.ctx.get_or_create("test", plan)
        self.ctx.mark_subtask_done(session, plan.subtasks[0].id, "result")
        status = self.ctx.get_status(session)
        assert "Completadas" in status


class TestSessionState:
    """Test SessionState data class."""

    def test_to_dict(self):
        subtasks = [SubTask(id="s1", agent="builder", description="code", dependencies=[])]
        plan = TaskPlan(session_id="sess-1", original_message="test", subtasks=subtasks)
        state = SessionState(
            session_id="sess-1",
            original_message="test",
            plan=plan,
        )
        d = state.to_dict()
        assert d["session_id"] == "sess-1"
        assert d["original_message"] == "test"
        assert "plan" in d
        assert not d["completed"]

    def test_to_dict_messages_limited(self):
        """Only last 20 messages are kept."""
        plan = TaskPlan(session_id="sess-1", original_message="test")
        state = SessionState(
            session_id="sess-1",
            original_message="test",
            plan=plan,
        )
        for i in range(30):
            state.messages.append({"role": "user", "content": f"msg-{i}"})
        d = state.to_dict()
        assert len(d["messages"]) <= 20
