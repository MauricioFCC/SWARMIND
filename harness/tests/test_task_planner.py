"""Tests for TaskPlanner — decomposition of user messages into DAG plans."""

import pytest
from harness.orchestrator.task_planner import (
    TaskPlanner,
    SubTask,
    TaskPlan,
    SUBTASK_TEMPLATES,
)


class TestTaskPlanner:
    """Verify that TaskPlanner correctly decomposes messages."""

    def setup_method(self):
        self.planner = TaskPlanner()

    def test_decompose_api(self):
        """'implementa una API en Rust' → template implement_api."""
        plan = self.planner.decompose("implementa una API REST en Rust")
        assert len(plan.subtasks) >= 3
        # First subtask should be builder
        assert plan.subtasks[0].agent == "builder"
        assert "API" in plan.subtasks[0].description or "api" in plan.subtasks[0].description

    def test_decompose_bugfix(self):
        """'fix bug en el login' → template fix_bug."""
        plan = self.planner.decompose("fix bug en el login que causa crash")
        assert len(plan.subtasks) >= 2
        # First should diagnose (scientist)
        assert plan.subtasks[0].agent == "scientist"
        assert "Diagnosticar" in plan.subtasks[0].description

    def test_decompose_research(self):
        """'investigar patrones de diseño' → template research."""
        plan = self.planner.decompose("investigar patrones de diseño para microservicios")
        assert len(plan.subtasks) >= 2
        assert plan.subtasks[0].agent == "scientist"
        assert "Recopilar" in plan.subtasks[0].description

    def test_decompose_refactor(self):
        """'refactorizar el modulo de auth' → template refactor."""
        plan = self.planner.decompose("refactorizar el modulo de auth para mejorar performance")
        assert len(plan.subtasks) >= 2
        assert plan.subtasks[0].agent == "scientist"
        assert "Analizar" in plan.subtasks[0].description

    def test_decompose_security(self):
        """'auditar seguridad del codigo' → template security_audit."""
        plan = self.planner.decompose("auditar seguridad del codigo y corregir vulnerabilidades")
        assert len(plan.subtasks) >= 2
        assert plan.subtasks[0].agent == "guardian"
        assert "Auditar" in plan.subtasks[0].description

    def test_decompose_deploy(self):
        """'desplegar a produccion' → template deploy."""
        plan = self.planner.decompose("desplegar a produccion la nueva version")
        assert len(plan.subtasks) >= 2
        assert plan.subtasks[0].agent == "builder"

    def test_decompose_docs(self):
        """'documentar la API' → template docs."""
        plan = self.planner.decompose("documentar la API con ejemplos y tutorial")
        assert len(plan.subtasks) >= 2
        assert plan.subtasks[0].agent == "scientist"

    def test_decompose_test(self):
        """'escribir tests para el modulo' → template test."""
        plan = self.planner.decompose("escribir tests con cobertura para el modulo de pagos")
        assert len(plan.subtasks) >= 2
        assert plan.subtasks[0].agent == "scientist"

    def test_decompose_database(self):
        """'crear esquema de base de datos' → template database."""
        plan = self.planner.decompose("crear esquema de base de datos para usuarios")
        assert len(plan.subtasks) >= 2
        assert plan.subtasks[0].agent == "scientist"

    def test_decompose_general(self):
        """Mensaje sin keywords claros → template general."""
        plan = self.planner.decompose("haz algo con el sistema")
        assert len(plan.subtasks) == 3
        assert plan.subtasks[0].agent == "scientist"

    def test_dag_levels_api(self):
        """API plan: level 0 = builder, level 1 = 3 guardian IN PARALELO."""
        plan = self.planner.decompose("implementa una API REST en Rust")
        levels = plan.get_levels()
        # Level 0: builder (code)
        # Level 1: guardian (tests + docs + security in parallel)
        assert len(levels) == 2
        assert len(levels[0]) == 1  # 1 builder
        assert levels[0][0].agent == "builder"
        assert len(levels[1]) == 3  # 3 guardian in parallel
        assert all(s.agent == "guardian" for s in levels[1])

    def test_dag_levels_bugfix(self):
        """Bugfix plan: diagnose → fix → test → verify (sequential)."""
        plan = self.planner.decompose("fix bug en producción")
        levels = plan.get_levels()
        assert len(levels) >= 3  # diagnose → fix → test+verify


class TestTaskPlan:
    """Test the TaskPlan data structure and methods."""

    def test_get_pending(self):
        subtasks = [
            SubTask(id="s1", agent="builder", description="code", dependencies=[]),
            SubTask(id="s2", agent="guardian", description="test", dependencies=["s1"]),
            SubTask(id="s3", agent="guardian", description="doc", dependencies=["s1"]),
        ]
        plan = TaskPlan(session_id="test", original_message="test", subtasks=subtasks)

        # Initially only s1 is pending
        pending = plan.get_pending()
        assert len(pending) == 1
        assert pending[0].id == "s1"

        # Mark s1 done — now s2 and s3 are pending
        plan.mark_completed("s1", "done")
        pending = plan.get_pending()
        assert len(pending) == 2
        assert {s.id for s in pending} == {"s2", "s3"}

    def test_get_next_level_sequential(self):
        subtasks = [
            SubTask(id="s1", agent="builder", description="code", dependencies=[]),
            SubTask(id="s2", agent="guardian", description="test", dependencies=["s1"]),
        ]
        plan = TaskPlan(session_id="test", original_message="test", subtasks=subtasks)

        next_lvl = plan.get_next_level()
        assert len(next_lvl) == 1
        assert next_lvl[0].id == "s1"

        plan.mark_completed("s1")
        next_lvl = plan.get_next_level()
        assert len(next_lvl) == 1
        assert next_lvl[0].id == "s2"

    def test_is_complete(self):
        subtasks = [
            SubTask(id="s1", agent="builder", description="code", dependencies=[]),
        ]
        plan = TaskPlan(session_id="test", original_message="test", subtasks=subtasks)
        assert not plan.is_complete()
        plan.mark_completed("s1")
        assert plan.is_complete()

    def test_mark_completed_unknown(self):
        plan = TaskPlan(session_id="test", original_message="test")
        # Should not raise
        plan.mark_completed("nonexistent", "result")

    def test_get_levels_empty(self):
        plan = TaskPlan(session_id="test", original_message="test")
        assert plan.get_levels() == []

    def test_to_dict(self):
        subtasks = [
            SubTask(id="s1", agent="builder", description="code", dependencies=[]),
        ]
        plan = TaskPlan(session_id="test", original_message="test msg", subtasks=subtasks)
        d = plan.to_dict()
        assert d["session_id"] == "test"
        assert d["original_message"] == "test msg"
        assert len(d["subtasks"]) == 1
        assert d["subtasks"][0]["agent"] == "builder"


class TestSubTask:
    """Test SubTask data class."""

    def test_to_dict(self):
        st = SubTask(
            id="st-1", agent="builder",
            description="Implementar API",
            dependencies=["st-0"],
            expected_output="Código funcionando",
            context_hint="usar Rust",
        )
        d = st.to_dict()
        assert d["id"] == "st-1"
        assert d["agent"] == "builder"
        assert d["description"] == "Implementar API"
        assert d["dependencies"] == ["st-0"]
        assert d["expected_output"] == "Código funcionando"
        assert d["context_hint"] == "usar Rust"
        assert not d["completed"]
        assert d["result"] == ""
