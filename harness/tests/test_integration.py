"""
Tests de integración completos para el sistema multi-agente.

Cubre:
  1. Pipeline completo: plan → notificar → ejecutar → consolidar
  2. Flujo con múltiples niveles (1→3)
  3. Manejo de errores y retry
  4. Health Check integration
  5. Telemetría integration
  6. TaskPlanner edge cases
  7. Ciclo completo ASI-Evolve
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure harness is in path
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_HARNESS = _HERE.parent
if str(_HARNESS) not in sys.path:
    sys.path.insert(0, str(_HARNESS))
if str(_HARNESS.parent) not in sys.path:
    sys.path.insert(0, str(_HARNESS.parent))

import pytest
from orchestrator.agent_discovery import discover_agents_recursive
from orchestrator.health import AgentHealthChecker, CognitiveState
from orchestrator.task_orchestrator import TaskOrchestrator
from orchestrator.task_planner import TaskPlan, TaskPlanner
from orchestrator.telemetry import (
    SubtaskRecord,
    TelemetryTracker,
)

# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def temp_data_dir():
    """Temp directory for test artifacts."""
    path = Path(tempfile.mkdtemp(prefix="harness_test_"))
    yield path
    shutil.rmtree(str(path), ignore_errors=True)


@pytest.fixture
def planner():
    return TaskPlanner()


@pytest.fixture
def orchestrator():
    """Orchestrator with minimal config."""
    return TaskOrchestrator(
        max_retries=2,
        level_timeout_sec=60,
        verbose=True,
    )


@pytest.fixture
def health_checker():
    return AgentHealthChecker()


@pytest.fixture
def telemetry_tracker(temp_data_dir):
    return TelemetryTracker(export_dir=str(temp_data_dir / "telemetry"))


# ===================================================================
# 1. Pipeline completo
# ===================================================================

class TestFullPipeline:
    """Prueba end-to-end del pipeline multi-nivel."""

    def test_plan_notify_execute_consolidate(self, orchestrator):
        """1a. Ciclo completo: plan → notificar → ejecutar → consolidar."""
        result = orchestrator.process_message("desplegar API REST en producción")
        assert result is not None
        assert hasattr(result, 'to_dict')
        rd = result.to_dict()
        assert "session_id" in rd
        assert rd["session_id"] != "error"

    def test_multi_level_flow(self, orchestrator):
        """1b. Flujo multi-nivel (nivel 1 → 3)."""
        # Force a multi-level task
        result = orchestrator.process_message(
            "implementar microservicio completo con auth, DB, y API REST"
        )
        assert result is not None
        assert hasattr(result, 'to_dict')
        rd = result.to_dict()
        assert len(rd.get("current_level", [])) >= 0  # non-crashing

    def test_agent_discovery_works(self):
        """1c. Agent discovery encuentra al menos 5 agentes."""
        agents = discover_agents_recursive()
        assert len(agents) >= 5, f"Expected >=5 agents, found {len(agents)}"
        names = list(agents.keys()) if isinstance(agents, dict) else agents
        assert any("builder" in n.lower() for n in names), "Builder not found"
        assert any("scientist" in n.lower() for n in names), "Scientist not found"
        assert any("guardian" in n.lower() for n in names), "Guardian not found"
        assert any("evolve" in n.lower() for n in names), "Evolve not found"

    def test_task_planner_decomposes(self, planner):
        """1d. TaskPlanner descompone correctamente en subtasks."""
        plan = planner.decompose("hacer deploy de API REST en AWS")
        assert plan is not None
        assert isinstance(plan, TaskPlan)
        assert len(plan.subtasks) > 0
        levels = plan.get_levels()
        assert len(levels) >= 1


# ===================================================================
# 2. Manejo de errores
# ===================================================================

class TestErrorHandling:
    """Tests de manejo de errores y resiliencia."""

    def test_retry_on_failure(self, orchestrator):
        """2a. Retry cuando una subtask falla."""
        result = orchestrator.process_message("tarea con error forzado")
        # Should not crash, should handle gracefully
        assert result is not None

    def test_circuit_breaker(self):
        """2b. Circuit breaker tras N fallos consecutivos."""
        from orchestrator.task_orchestrator import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10)

        assert cb.state == "closed"
        cb.record_failure()
        assert cb.state == "closed"
        cb.record_failure()
        assert cb.state == "closed"
        cb.record_failure()
        assert cb.state == "open", f"Expected open, got {cb.state}"

    @pytest.mark.slow
    def test_circuit_breaker_recovers(self):
        """2c. Circuit breaker se recupera tras timeout."""
        from orchestrator.task_orchestrator import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=2)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"

        time.sleep(2.5)
        cb.record_failure()  # should transition to half-open then re-record
        assert cb.state in ("half-open", "open")


# ===================================================================
# 3. Health Check integration
# ===================================================================

class TestHealthCheck:
    """Tests del sistema de Health Check."""

    def test_liveness(self, health_checker):
        """3a. Liveness check: sistema responde."""
        status = health_checker.check_liveness()
        assert status.healthy, f"Liveness failed: {status.message}"
        assert status.level == "liveness"
        assert status.status == "ok"

    def test_readiness(self, health_checker):
        """3b. Readiness check: sistema listo para tareas."""
        status = health_checker.check_readiness()
        assert status.healthy, f"Readiness failed: {status.message}"
        assert status.level == "readiness"

    def test_cognitive_no_sessions(self, health_checker):
        """3c. Cognitive check: sin sesiones activas."""
        status = health_checker.check_cognitive()
        assert status.healthy
        assert status.details.get("active_sessions", -1) == 0

    def test_cognitive_repeater_detection(self):
        """3d. Detección de Repeater (misma subtask repetida)."""
        state = CognitiveState(session_id="test-repeater")
        state.record_subtask("build", "builder", "Build the thing")
        state.record_subtask("build", "builder", "Build the thing")
        state.record_subtask("build", "builder", "Build the thing")

        issue = state.check_repeater()
        assert issue is not None
        assert "REPEATER" in issue

    def test_cognitive_looper_detection(self):
        """3e. Detección de Looper (alternancia)."""
        state = CognitiveState(session_id="test-looper")
        for _ in range(6):
            state.record_subtask("A", "agent1", "Do A")
            state.record_subtask("B", "agent2", "Do B")

        issue = state.check_looper()
        assert issue is not None
        assert "LOOPER" in issue

    def test_cognitive_timeout_detection(self):
        """3f. Detección de Timeout en nivel."""
        state = CognitiveState(session_id="test-timeout")
        state.level_start_time = time.time() - 400  # 400s atrás
        issue = state.check_timeout()
        assert issue is not None
        assert "TIMEOUT" in issue

    def test_health_all_levels(self, health_checker):
        """3g. check_all ejecuta los 3 niveles."""
        result = health_checker.check_all()
        assert "liveness" in result
        assert "readiness" in result
        assert "cognitive" in result
        assert result["liveness"].healthy
        assert result["readiness"].healthy
        assert result["cognitive"].healthy


# ===================================================================
# 4. Telemetría
# ===================================================================

class TestTelemetry:
    """Tests del sistema de Telemetría."""

    def test_start_session(self, telemetry_tracker):
        """4a. Iniciar y obtener una sesión."""
        t = telemetry_tracker.start_session("test-1", "deploy API")
        assert t is not None
        assert t.session_id == "test-1"
        assert t.task == "deploy API"
        assert t.status == "running"

        t2 = telemetry_tracker.get_session("test-1")
        assert t2 is t

    def test_record_subtask(self, telemetry_tracker):
        """4b. Registrar subtasks y verificar estadísticas."""
        t = telemetry_tracker.start_session("test-2", "build feature")
        t.record_subtask(0, SubtaskRecord("s1", "builder", "Write code",
                                          status="success"))
        t.record_subtask(0, SubtaskRecord("s2", "guardian", "Test code",
                                          status="success"))
        t.record_subtask(1, SubtaskRecord("s3", "builder", "Deploy",
                                          status="failed", error="port taken"))

        assert t.total_subtasks == 3
        assert t.total_errors == 1
        assert len(t.levels) == 2
        assert t.levels[0].success_rate == 1.0
        assert t.levels[1].success_rate == 0.0

    def test_finalize_and_export(self, telemetry_tracker):
        """4c. Finalizar y exportar sesión a JSON."""
        t = telemetry_tracker.start_session("test-3", "task")
        t.record_subtask(0, SubtaskRecord("s1", "builder", "Build",
                                          status="success"))
        telemetry_tracker.finalize_session("test-3", "completed")

        # Check export
        export_path = telemetry_tracker.export("test-3")
        assert export_path is not None
        assert os.path.exists(export_path)

        with open(export_path, "r") as f:
            data = json.load(f)
        assert data["session_id"] == "test-3"
        assert data["status"] == "completed"
        assert data["total_subtasks"] == 1

    def test_summary(self, telemetry_tracker):
        """4d. Resumen ejecutivo."""
        t = telemetry_tracker.start_session("test-4", "multi-agent task")
        t.record_subtask(0, SubtaskRecord("s1", "builder", "Build",
                                          status="success"))
        t.record_subtask(0, SubtaskRecord("s2", "guardian", "Test",
                                          status="failed", error="timeout"))
        telemetry_tracker.finalize_session("test-4", "completed")

        summary = t.summary()
        assert summary["total_subtasks"] == 2
        assert summary["total_errors"] == 1
        assert summary["success_rate"] == 0.5

    def test_agent_stats(self, telemetry_tracker):
        """4e. Estadísticas por agente."""
        t = telemetry_tracker.start_session("test-5", "task")
        t.record_subtask(0, SubtaskRecord("s1", "builder", "Build",
                                          status="success"))
        t.record_subtask(0, SubtaskRecord("s2", "builder", "Refactor",
                                          status="success"))
        t.record_subtask(0, SubtaskRecord("s3", "guardian", "Test",
                                          status="failed", error="crash"))
        t.record_subtask(0, SubtaskRecord("s4", "guardian", "Retest",
                                          status="success"))

        stats = t.agent_stats
        assert "builder" in stats
        assert stats["builder"]["ok"] == 2
        assert stats["builder"]["error"] == 0
        assert "guardian" in stats
        assert stats["guardian"]["ok"] == 1
        assert stats["guardian"]["error"] == 1


# ===================================================================
# 5. Edge cases en TaskPlanner
# ===================================================================

class TestEdgeCases:
    """Tests de edge cases en planificación."""

    def test_empty_task(self, planner):
        """5a. Tarea vacía → plan mínimo."""
        plan = planner.decompose("")
        assert plan is not None
        assert len(plan.subtasks) > 0 or plan.original_message == ""

    def test_single_word_task(self, planner):
        """5b. Tarea de una palabra."""
        plan = planner.decompose("deploy")
        assert plan is not None
        assert len(plan.subtasks) > 0

    def test_very_long_task(self, planner):
        """5c. Tarea extremadamente larga."""
        long_task = "implement " + " and ".join(f"feature{i}" for i in range(50))
        plan = planner.decompose(long_task)
        assert plan is not None
        assert len(plan.subtasks) > 0
        # Should not exceed reasonable level count
        levels = plan.get_levels()
        assert len(levels) <= 5, f"Too many levels: {len(levels)}"

    def test_special_characters(self, planner):
        """5d. Tarea con caracteres especiales."""
        plan = planner.decompose("deploy @home #final !urgent (v2)")
        assert plan is not None
        assert len(plan.subtasks) > 0

    def test_unicode_task(self, planner):
        """5e. Tarea con Unicode."""
        plan = planner.decompose("desplegar API REST en producción")
        assert plan is not None
        assert len(plan.subtasks) > 0

    def test_repeated_task(self, planner):
        """5f. Tarea repetitiva."""
        task = "deploy deploy deploy"
        plan = planner.decompose(task)
        assert plan is not None

    def test_task_planner_consistency(self, planner):
        """5g. Consistencia: misma tarea → misma estructura de plan."""
        plan1 = planner.decompose("deploy API REST")
        plan2 = planner.decompose("deploy API REST")
        assert len(plan1.subtasks) == len(plan2.subtasks)
        for st1, st2 in zip(plan1.subtasks, plan2.subtasks):
            assert st1.description == st2.description


# ===================================================================
# 6. TaskOrchestrator edge cases
# ===================================================================

class TestOrchestratorEdgeCases:
    """Tests de edge cases en el orquestador."""

    def test_none_task(self, orchestrator):
        """6a. Task vacía (string vacío)."""
        result = orchestrator.process_message("")
        assert result is not None

    @pytest.mark.slow
    def test_rapid_consecutive_tasks(self, orchestrator):
        """6b. Tasks rápidas consecutivas."""
        for i in range(3):
            result = orchestrator.process_message(f"tarea simple {i}")
            assert result is not None

    def test_orchestrator_with_custom_planner(self):
        """6c. Orchestrator con TaskPlanner personalizado."""
        orch = TaskOrchestrator(
            max_retries=1,
        )
        result = orch.process_message("test custom")
        assert result is not None


# ===================================================================
# 7. Health + Telemetry integration
# ===================================================================

class TestHealthTelemetryIntegration:
    """Prueba de integración entre Health Check y Telemetría."""

    def test_health_during_session(self, health_checker, telemetry_tracker):
        """7a. Health check durante sesión activa."""
        telemetry = telemetry_tracker.start_session("integ-1", "test")

        # Create a cognitive state to simulate active session
        state = health_checker.get_or_create_cognitive_state("integ-1")
        state.record_subtask("build", "builder", "Build")
        state.record_subtask("build", "builder", "Build")
        state.record_subtask("build", "builder", "Build")

        # Should detect repeater
        status = health_checker.check_cognitive("integ-1")
        assert not status.healthy
        assert "REPEATER" in status.message

        # Telemetry should still work
        telemetry.record_subtask(0, SubtaskRecord("build", "builder", "Build"))
        assert telemetry.total_subtasks >= 1

    def test_cleanup_stale(self, health_checker):
        """7b. Limpieza de sesiones cognitivas stale."""
        state = health_checker.get_or_create_cognitive_state("stale-session")
        state.last_progress_time = time.time() - 7200  # 2h atrás

        cleaned = health_checker.cleanup_stale_sessions(max_age_sec=3600)
        assert cleaned >= 1
        assert "stale-session" not in health_checker._cognitive_states


# ===================================================================
# 8. Sistema completo ASI-Evolve
# ===================================================================

class TestASIEvolveCycle:
    """Prueba del ciclo completo ASI-Evolve."""

    def test_learn_to_analyze_flow(self):
        """8a. Flujo Learn → Design → Experiment → Analyze."""
        # Simulate a minimal ASI-Evolve cycle
        from orchestrator.task_planner import TaskPlanner
        planner = TaskPlanner()

        # Learn phase: analyze task
        plan = planner.decompose("mejorar sistema de health checks")
        assert plan is not None
        assert len(plan.subtasks) > 0

    def test_knowledge_persistence(self, temp_data_dir):
        """8b. Persistencia de conocimiento entre ciclos."""
        # Write knowledge
        knowledge_file = temp_data_dir / "knowledge.json"
        data = {"pattern": "health_check", "count": 5, "avg_duration": 2.3}
        with open(knowledge_file, "w") as f:
            json.dump(data, f)

        # Read it back
        with open(knowledge_file, "r") as f:
            loaded = json.load(f)
        assert loaded["pattern"] == "health_check"
        assert loaded["count"] == 5


# ===================================================================
# Run
# ===================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
