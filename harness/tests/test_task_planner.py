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
        """'implementa una API REST en Rust' → template dinamico."""
        plan = self.planner.decompose("implementa una API REST en Rust")
        assert len(plan.subtasks) >= 3
        # Dynamic scaling: primero coordinator (PLAN), luego builders
        assert plan.subtasks[0].agent in ("coordinator", "builder")

    def test_decompose_bugfix(self):
        """'fix bug en el login' → template fix_bug."""
        plan = self.planner.decompose("fix bug en el login que causa crash")
        assert len(plan.subtasks) >= 2
        assert plan.subtasks[0].agent == "scientist"
        # Case-insensitive: desc has "DIAGNOSTICO" or "Diagnosticar"
        desc_upper = plan.subtasks[0].description.upper()
        assert "DIAGNOSTIC" in desc_upper

    def test_decompose_research(self):
        """'investigar patrones de diseño' → template research."""
        plan = self.planner.decompose("investigar patrones de diseño para microservicios")
        assert len(plan.subtasks) >= 2
        assert plan.subtasks[0].agent == "scientist"
        desc_upper = plan.subtasks[0].description.upper()
        assert "RECOPILAR" in desc_upper

    def test_decompose_refactor(self):
        """'refactorizar el modulo de auth' → template refactor."""
        plan = self.planner.decompose("refactorizar el modulo de auth para mejorar performance")
        assert len(plan.subtasks) >= 2
        assert plan.subtasks[0].agent == "scientist"
        desc_upper = plan.subtasks[0].description.upper()
        assert "ANALISIS" in desc_upper or "ANALIZAR" in desc_upper

    def test_decompose_security(self):
        """'auditar seguridad del codigo' → template security_audit."""
        plan = self.planner.decompose("auditar seguridad del codigo y corregir vulnerabilidades")
        assert len(plan.subtasks) >= 2
        assert plan.subtasks[0].agent == "guardian"
        desc_upper = plan.subtasks[0].description.upper()
        assert "AUDITAR" in desc_upper

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
        """'crear esquema de base de datos' → template dinamico."""
        plan = self.planner.decompose("crear esquema de base de datos para usuarios")
        assert len(plan.subtasks) >= 2
        # Dynamic scaling: primer agente puede ser coordinator (plan) o builder
        assert plan.subtasks[0].agent in ("builder", "scientist", "coordinator")

    def test_decompose_general(self):
        """Mensaje sin keywords claros → template general."""
        plan = self.planner.decompose("haz algo con el sistema")
        # general template: 4 subtasks
        assert len(plan.subtasks) >= 3
        assert plan.subtasks[0].agent in ("builder", "guardian", "scientist", "coordinator")

    def test_dag_levels_api(self):
        """API plan dinamico: escala segun alcance."""
        plan = self.planner.decompose("implementa una API REST en Rust")
        levels = plan.get_levels()
        # Dynamic: puede tener 3+ niveles o template especifico
        assert len(levels) >= 1
        assert levels[0][0].agent in ("builder", "coordinator")

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

    def test_get_current_level_num_initial(self):
        """Nuevo plan sin completar → nivel 0."""
        subtasks = [
            SubTask(id="s1", agent="builder", description="code", dependencies=[]),
            SubTask(id="s2", agent="guardian", description="test", dependencies=["s1"]),
        ]
        plan = TaskPlan(session_id="test", original_message="test", subtasks=subtasks)
        assert plan.get_current_level_num() == 0  # Nivel 0: s1

    def test_get_current_level_num_after_first(self):
        """Completar nivel 0 → nivel 1."""
        subtasks = [
            SubTask(id="s1", agent="builder", description="code", dependencies=[]),
            SubTask(id="s2", agent="guardian", description="test", dependencies=["s1"]),
        ]
        plan = TaskPlan(session_id="test", original_message="test", subtasks=subtasks)
        plan.mark_completed("s1")
        assert plan.get_current_level_num() == 1  # Nivel 1: s2

    def test_get_current_level_num_all_complete(self):
        """Todos completos → len(levels)."""
        subtasks = [
            SubTask(id="s1", agent="builder", description="code", dependencies=[]),
        ]
        plan = TaskPlan(session_id="test", original_message="test", subtasks=subtasks)
        plan.mark_completed("s1")
        assert plan.get_current_level_num() == 1

    def test_get_current_level_num_empty(self):
        """Plan vacio → 0."""
        plan = TaskPlan(session_id="test", original_message="test")
        assert plan.get_current_level_num() == 0

    def test_get_summary(self):
        """get_summary debe incluir el progreso."""
        subtasks = [
            SubTask(id="s1", agent="builder", description="code", dependencies=[]),
        ]
        plan = TaskPlan(session_id="test", original_message="test task", subtasks=subtasks)
        summary = plan.get_summary()
        assert "test task" in summary or "Plan" in summary
        assert "0/1" in summary

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
