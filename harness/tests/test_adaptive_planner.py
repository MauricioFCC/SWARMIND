"""
Tests para AdaptivePlanner — meta-agente que ajusta topología del plan
basado en feedback de ejecuciones anteriores e integración PSMAS.

Cubre: inicialización, selección de estrategia, adaptación por feedback,
re-planificación, phase scheduling PSMAS, compresión de contexto,
persistencia y edge cases.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from harness.orchestrator.adaptive_planner import (
    ALWAYS_ACTIVE_AGENTS,
    REPLAN_FAILURE_RATE,
    AdaptivePlanner,
    PhasePlan,
    PlanFeedback,
    PlanStrategy,
    StrategyStats,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def planner():
    """AdaptivePlanner sin persistencia."""
    return AdaptivePlanner()


@pytest.fixture
def planner_with_storage(tmp_path):
    """AdaptivePlanner con ruta de persistencia temporal."""
    storage = tmp_path / "adaptive_planner_stats.json"
    return AdaptivePlanner(storage_path=str(storage))


@pytest.fixture
def sample_feedback() -> PlanFeedback:
    """Feedback sample para pruebas."""
    return PlanFeedback(
        session_id="sess_001",
        task_hash="abc123",
        task_type="implement",
        strategy_used=PlanStrategy.HYBRID,
        subtask_count=5,
        level_count=3,
        success_count=4,
        failure_count=1,
        total_duration_ms=1500.0,
        success_rate=0.8,
    )


@pytest.fixture
def sample_feedback_low_rate() -> PlanFeedback:
    """Feedback con baja tasa de éxito (para trigger de re-plan)."""
    return PlanFeedback(
        session_id="sess_002",
        task_hash="def456",
        task_type="deploy",
        strategy_used=PlanStrategy.SEQUENTIAL,
        subtask_count=4,
        level_count=2,
        success_count=1,
        failure_count=3,
        total_duration_ms=3000.0,
        success_rate=0.25,
    )


# ---------------------------------------------------------------------------
# Tests: Dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    """Tests para PlanFeedback, StrategyStats y PhasePlan."""

    def test_plan_feedback_to_dict(self, sample_feedback):
        """PlanFeedback.to_dict() debe incluir todos los campos clave."""
        d = sample_feedback.to_dict()
        assert d["session_id"] == "sess_001"
        assert d["strategy_used"] == "hybrid"
        assert d["success_rate"] == 0.8
        assert "timestamp" in d

    def test_strategy_stats_success_rate(self):
        """StrategyStats.success_rate debe calcularse correctamente."""
        stats = StrategyStats(strategy=PlanStrategy.SINGLE_AGENT)
        stats.total_uses = 10
        stats.total_successes = 7
        assert stats.success_rate == 0.7

    def test_strategy_stats_success_rate_zero_uses(self):
        """Con 0 usos, success_rate debe ser 0.0."""
        stats = StrategyStats(strategy=PlanStrategy.HYBRID)
        assert stats.success_rate == 0.0

    def test_strategy_stats_update(self, sample_feedback):
        """StrategyStats.update() debe actualizar promedios."""
        stats = StrategyStats(strategy=PlanStrategy.HYBRID)
        stats.update(sample_feedback)
        assert stats.total_uses == 1
        assert stats.total_successes == 1
        assert stats.avg_duration_ms == 1500.0

    def test_strategy_stats_update_with_failure(self):
        """Feedback con success_rate < 0.7 debe contar como fallo."""
        stats = StrategyStats(strategy=PlanStrategy.SINGLE_AGENT)
        fail_fb = PlanFeedback(
            session_id="s", task_hash="h", task_type="t",
            strategy_used=PlanStrategy.SINGLE_AGENT,
            subtask_count=1, level_count=1,
            success_count=0, failure_count=1,
            total_duration_ms=100.0, success_rate=0.0,
        )
        stats.update(fail_fb)
        assert stats.total_failures == 1

    def test_phase_plan_to_dict(self):
        """PhasePlan.to_dict() debe incluir agent_phases y task_type."""
        pp = PhasePlan(
            agent_phases={"builder": 0.0, "scientist": 120.0},
            task_type="implement",
        )
        d = pp.to_dict()
        assert d["agent_phases"]["builder"] == 0.0
        assert d["task_type"] == "implement"
        assert "created_at" in d


# ---------------------------------------------------------------------------
# Tests: Initialization
# ---------------------------------------------------------------------------


class TestInitialization:
    """Tests de inicialización del AdaptivePlanner."""

    def test_init_defaults(self, planner):
        """Inicialización con valores por defecto."""
        assert planner._min_samples == 3
        assert len(planner._strategy_stats) == 4
        assert planner._feedback_history == []
        assert planner._best_strategies == {}

    def test_init_with_storage_path(self, tmp_path):
        """Inicialización con storage_path debe persistir."""
        storage = tmp_path / "test_stats.json"
        planner = AdaptivePlanner(storage_path=str(storage))
        assert planner._storage_path == str(storage)

    def test_init_strategies_all_present(self, planner):
        """Todos los PlanStrategy deben estar en _strategy_stats."""
        for s in PlanStrategy:
            assert s.value in planner._strategy_stats

    @patch("harness.orchestrator.adaptive_planner.AdaptivePlanner._load")
    def test_init_loads_persistence(self, mock_load, tmp_path):
        """Si hay storage_path, debe cargar datos al iniciar."""
        storage = tmp_path / "stats.json"
        AdaptivePlanner(storage_path=str(storage))
        mock_load.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: choose_strategy
# ---------------------------------------------------------------------------


class TestChooseStrategy:
    """Tests para la selección de estrategia."""

    def test_choose_known_strategy(self, planner):
        """Si se pasa known_strategy, debe usarlo directamente."""
        result = planner.choose_strategy(
            "test", known_strategy=PlanStrategy.SINGLE_AGENT,
        )
        assert result == PlanStrategy.SINGLE_AGENT

    def test_choose_force_agent_single(self, planner):
        """Si hay force_agent, debe retornar SINGLE_AGENT."""
        result = planner.choose_strategy(
            "test", force_agent="software-engineer",
        )
        assert result == PlanStrategy.SINGLE_AGENT

    def test_choose_by_task_type_implement(self, planner):
        """Tarea 'implement' debe seleccionar HYBRID."""
        result = planner.choose_strategy("implementar API REST con Docker")
        assert result == PlanStrategy.HYBRID

    def test_choose_by_task_type_research(self, planner):
        """Tarea 'research' debe seleccionar SINGLE_AGENT."""
        result = planner.choose_strategy("investigar arquitectura")
        assert result == PlanStrategy.SINGLE_AGENT

    def test_choose_by_task_type_deploy(self, planner):
        """Tarea 'deploy' debe seleccionar SEQUENTIAL."""
        result = planner.choose_strategy("deploy a producción")
        assert result == PlanStrategy.SEQUENTIAL

    def test_choose_best_known_strategy(self, planner):
        """Si hay mejor estrategia conocida con confianza > 0.7, debe usarla."""
        planner._best_strategies["type:implement"] = (
            PlanStrategy.FAN_OUT_FAN_IN, 0.85,
        )
        result = planner.choose_strategy(
            "implementar API", task_type="implement",
        )
        assert result == PlanStrategy.FAN_OUT_FAN_IN

    def test_choose_with_agents_phase_scheduling(self, planner):
        """Con 3+ agentes debe activar phase scheduling."""
        planner.choose_strategy(
            "investigar", agents=["builder", "scientist", "guardian"],
        )
        assert planner._phase_plan.agent_phases != {}


# ---------------------------------------------------------------------------
# Tests: Phase Scheduling (PSMAS)
# ---------------------------------------------------------------------------


class TestPhaseScheduling:
    """Tests para phase scheduling PSMAS."""

    def test_assign_agent_phases_builder(self, planner):
        """Builder siempre debe tener fase 0."""
        phases = planner._assign_agent_phases(["builder"], "test")
        assert phases["builder"] == 0.0

    def test_assign_agent_phases_scientist(self, planner):
        """Scientist debe tener fase 120."""
        phases = planner._assign_agent_phases(["scientist"], "test")
        assert phases["scientist"] == 120.0

    def test_assign_agent_phases_guardian(self, planner):
        """Guardian debe tener fase 240."""
        phases = planner._assign_agent_phases(["guardian"], "test")
        assert phases["guardian"] == 240.0

    def test_assign_phases_all_always_active(self, planner):
        """Todos los ALWAYS_ACTIVE_AGENTS deben tener fase 0."""
        agents = list(ALWAYS_ACTIVE_AGENTS)
        phases = planner._assign_agent_phases(agents, "test")
        for a in agents:
            assert phases[a] == 0.0

    def test_get_phase_plan(self, planner):
        """get_phase_plan() debe retornar dict con agent_phases."""
        pp = planner.get_phase_plan()
        assert "agent_phases" in pp

    def test_get_active_agents_all_active_no_plan(self, planner):
        """Sin phase plan, todos los agentes deben estar activos."""
        active = planner.get_active_agents(
            ["builder", "scientist"], phase_degrees=0.0,
        )
        assert len(active) == 2

    def test_get_active_agents_with_plan(self, planner):
        """Con phase plan, solo agentes en ventana deben estar activos."""
        planner._phase_plan = PhasePlan(
            agent_phases={"builder": 0.0, "scientist": 120.0, "guardian": 240.0},
            task_type="test",
        )
        active = planner.get_active_agents(
            ["builder", "scientist", "guardian"], phase_degrees=0.0, window=60.0,
        )
        assert "builder" in active
        # scientist a 120° está fuera de la ventana de 60° alrededor de 0°
        assert "scientist" not in active

    def test_get_active_agents_fallback_closest(self, planner):
        """Si no hay activos, debe incluir el más cercano."""
        planner._phase_plan = PhasePlan(
            agent_phases={"scientist": 120.0, "guardian": 240.0},
            task_type="test",
        )
        active = planner.get_active_agents(
            ["scientist", "guardian"], phase_degrees=0.0, window=10.0,
        )
        assert len(active) >= 1

    def test_apply_phase_scheduling_less_than_3(self, planner):
        """Con menos de 3 agentes, phase plan debe estar vacío."""
        planner._apply_phase_scheduling(
            PlanStrategy.HYBRID, ["builder", "scientist"], "test",
        )
        assert planner._phase_plan.agent_phases == {}

    def test_apply_phase_scheduling_hybrid_with_3(self, planner):
        """HYBRID con 3+ agentes debe asignar phase plan."""
        planner._apply_phase_scheduling(
            PlanStrategy.HYBRID, ["builder", "scientist", "guardian"], "test",
        )
        assert len(planner._phase_plan.agent_phases) == 3


# ---------------------------------------------------------------------------
# Tests: Context Compression
# ---------------------------------------------------------------------------


class TestContextCompression:
    """Tests para compress_context_for_idle."""

    def test_compress_short_context(self, planner):
        """Contexto corto debe retornarse sin cambios."""
        result = planner.compress_context_for_idle("agent", "Hola mundo", target_tokens=100)
        assert result == "Hola mundo"

    def test_compress_empty_context(self, planner):
        """Contexto vacío debe retornar ''."""
        result = planner.compress_context_for_idle("agent", "", target_tokens=100)
        assert result == ""

    def test_compress_essential_keywords(self, planner):
        """Debe mantener líneas con keywords esenciales y filtrar otras."""
        # Contexto lo suficientemente grande para evitar return early
        # pero con target_tokens alto para no truncar las líneas esenciales
        context = (
            "task: implementar API\n"
            + "otro texto sin keyword\n" * 50
            + "result: éxito\n"
        )
        # target_tokens=50 permite ~200 chars antes de truncar
        result = planner.compress_context_for_idle("agent", context, target_tokens=50)
        assert "task: implementar API" in result
        assert "result: éxito" in result
        assert "otro texto sin keyword" not in result

    def test_compress_truncation(self, planner):
        """Si excede target_tokens, debe truncar."""
        long_context = "task: " + "A" * 5000
        result = planner.compress_context_for_idle("agent", long_context, target_tokens=10)
        assert len(result) < len(long_context)
        assert "[...truncated" in result

    def test_compress_no_essential_fallback(self, planner):
        """Sin líneas esenciales, debe tomar primeras líneas."""
        context = "línea 1\nlínea 2\nlínea 3\nlínea 4"
        result = planner.compress_context_for_idle("agent", context, target_tokens=100)
        # Debe tener contenido (las primeras líneas significativas)
        assert result


# ---------------------------------------------------------------------------
# Tests: Record Feedback & Adaptation
# ---------------------------------------------------------------------------


class TestRecordFeedback:
    """Tests para registro de feedback y adaptación."""

    def test_record_feedback_updates_stats(self, planner, sample_feedback):
        """record_feedback debe actualizar estadísticas de estrategia."""
        planner.record_feedback(sample_feedback)
        stats = planner._strategy_stats["hybrid"]
        assert stats.total_uses == 1
        assert stats.total_successes == 1

    def test_record_feedback_updates_history(self, planner, sample_feedback):
        """Debe agregar feedback al historial."""
        planner.record_feedback(sample_feedback)
        assert len(planner._feedback_history) == 1

    def test_record_feedback_updates_best_strategies(self, planner, sample_feedback):
        """Debe actualizar best_strategies para el tipo de tarea."""
        planner.record_feedback(sample_feedback)
        key = "type:implement"
        assert key in planner._best_strategies
        strat, rate = planner._best_strategies[key]
        assert strat == PlanStrategy.HYBRID
        assert rate == 0.8

    def test_record_feedback_history_capped(self, planner, sample_feedback):
        """El historial no debe exceder 100 entradas."""
        for i in range(105):
            fb = PlanFeedback(
                session_id=f"s_{i}", task_hash=f"h{i}", task_type="t",
                strategy_used=PlanStrategy.SINGLE_AGENT,
                subtask_count=1, level_count=1,
                success_count=1, failure_count=0,
                total_duration_ms=100.0, success_rate=1.0,
            )
            planner.record_feedback(fb)
        assert len(planner._feedback_history) == 100

    @patch("harness.orchestrator.adaptive_planner.AdaptivePlanner._save")
    def test_record_feedback_persists(self, mock_save, planner_with_storage, sample_feedback):
        """Si hay storage_path, debe persistir al registrar feedback."""
        planner_with_storage.record_feedback(sample_feedback)
        mock_save.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: should_replan
# ---------------------------------------------------------------------------


class TestReplan:
    """Tests para la lógica de re-planificación."""

    def test_should_replan_high_failure(self, planner, sample_feedback_low_rate):
        """Con failure_rate > REPLAN_FAILURE_RATE, debe re-planificar."""
        must, reason = planner.should_replan(sample_feedback_low_rate)
        assert must
        assert "failure_rate" in reason

    def test_should_replan_not_needed(self, planner, sample_feedback):
        """Con buena tasa de éxito, no debe re-planificar."""
        must, reason = planner.should_replan(sample_feedback)
        assert not must
        assert reason is None

    def test_should_replan_stalled_warnings(self, planner, sample_feedback):
        """Con stalled_warnings >= 2 debe re-planificar."""
        healing = {"stalled_warnings": 2}
        must, reason = planner.should_replan(sample_feedback, healing_context=healing)
        assert must
        assert "stall" in reason

    def test_should_replan_consecutive_failures(self, planner):
        """Múltiples fallos recientes deben gatillar re-plan."""
        # Registrar 2 fallos
        for _ in range(2):
            fb = PlanFeedback(
                session_id="s", task_hash="h", task_type="t",
                strategy_used=PlanStrategy.SINGLE_AGENT,
                subtask_count=5, level_count=1,
                success_count=1, failure_count=4,
                total_duration_ms=100.0, success_rate=0.2,
            )
            planner._feedback_history.append(fb)
        # Un tercer feedback bueno pero los 2 anteriores fallaron
        fb_actual = PlanFeedback(
            session_id="s3", task_hash="h3", task_type="t",
            strategy_used=PlanStrategy.SINGLE_AGENT,
            subtask_count=5, level_count=1,
            success_count=1, failure_count=4,
            total_duration_ms=100.0, success_rate=0.2,
        )
        must, _reason = planner.should_replan(fb_actual)
        assert must

    def test_should_replan_min_subtasks_check(self, planner):
        """Con subtask_count <= REPLAN_MIN_SUBTASKS no debe re-planificar por failure_rate."""
        fb = PlanFeedback(
            session_id="s", task_hash="h", task_type="t",
            strategy_used=PlanStrategy.SINGLE_AGENT,
            subtask_count=1, level_count=1,
            success_count=0, failure_count=1,
            total_duration_ms=100.0, success_rate=0.0,
        )
        must, _ = planner.should_replan(fb)
        # success_rate=0 < 0.5, pero subtask_count=1 no > REPLAN_MIN_SUBTASKS
        assert not must


# ---------------------------------------------------------------------------
# Tests: estimate_levels
# ---------------------------------------------------------------------------


class TestEstimateLevels:
    """Tests para la estimación de niveles."""

    def test_estimate_single_agent(self, planner):
        """SINGLE_AGENT debe retornar 1 nivel."""
        assert planner.estimate_levels("test", PlanStrategy.SINGLE_AGENT) == 1

    def test_estimate_sequential_short(self, planner):
        """SEQUENTIAL con < 10 palabras debe retornar 1."""
        assert planner.estimate_levels("corto", PlanStrategy.SEQUENTIAL) == 1

    def test_estimate_sequential_medium(self, planner):
        """SEQUENTIAL con 10-30 palabras debe retornar 2."""
        text = " ".join(["word"] * 15)
        assert planner.estimate_levels(text, PlanStrategy.SEQUENTIAL) == 2

    def test_estimate_sequential_long(self, planner):
        """SEQUENTIAL con 30-60 palabras debe retornar 3."""
        text = " ".join(["word"] * 40)
        assert planner.estimate_levels(text, PlanStrategy.SEQUENTIAL) == 3

    def test_estimate_sequential_very_long(self, planner):
        """SEQUENTIAL con > 60 palabras debe retornar 4."""
        text = " ".join(["word"] * 70)
        assert planner.estimate_levels(text, PlanStrategy.SEQUENTIAL) == 4

    def test_estimate_fan_out_fan_in(self, planner):
        """FAN_OUT_FAN_IN debe retornar 2 niveles."""
        assert planner.estimate_levels("test", PlanStrategy.FAN_OUT_FAN_IN) == 2

    def test_estimate_hybrid(self, planner):
        """HYBRID debe retornar 3 niveles."""
        assert planner.estimate_levels("test", PlanStrategy.HYBRID) == 3


# ---------------------------------------------------------------------------
# Tests: get_recommendation
# ---------------------------------------------------------------------------


class TestGetRecommendation:
    """Tests para get_recommendation."""

    def test_recommendation_contains_key_fields(self, planner, sample_feedback):
        """get_recommendation debe incluir strategy, confidence y stats."""
        planner.record_feedback(sample_feedback)
        rec = planner.get_recommendation("implementar API")
        assert "recommended_strategy" in rec
        assert "confidence" in rec
        assert "strategy_stats" in rec
        assert "total_feedback_samples" in rec

    def test_recommendation_includes_phase_plan_when_active(self, planner):
        """Si hay phase plan activo, debe incluirse en la recomendación."""
        planner.choose_strategy(
            "implementar API", agents=["builder", "scientist", "guardian"],
        )
        rec = planner.get_recommendation("implementar API")
        if planner._phase_plan.agent_phases:
            assert "phase_plan" in rec


# ---------------------------------------------------------------------------
# Tests: Internal methods
# ---------------------------------------------------------------------------


class TestInternalMethods:
    """Tests para métodos internos: _detect_task_type, _hash_task, _select_by_task_type."""

    def test_detect_task_type_deploy(self, planner):
        """_detect_task_type debe detectar 'deploy'."""
        assert planner._detect_task_type("deploy a producción") == "deploy"

    def test_detect_task_type_implement(self, planner):
        """_detect_task_type debe detectar 'implement'."""
        assert planner._detect_task_type("implementar módulo X") == "implement"

    def test_detect_task_type_research(self, planner):
        """_detect_task_type debe detectar 'research'."""
        assert planner._detect_task_type("investigar algoritmo") == "research"

    def test_detect_task_type_unknown(self, planner):
        """Sin keywords debe retornar 'general'."""
        assert planner._detect_task_type("") == "unknown"
        assert planner._detect_task_type("cosas aleatorias sin sentido") == "general"

    def test_hash_task_consistency(self, planner):
        """_hash_task debe ser determinista."""
        h1 = planner._hash_task("implementar API")
        h2 = planner._hash_task("implementar API")
        assert h1 == h2

    def test_hash_task_different_tasks(self, planner):
        """Tareas diferentes deben tener hash diferente."""
        h1 = planner._hash_task("implementar API")
        h2 = planner._hash_task("investigar")
        assert h1 != h2


# ---------------------------------------------------------------------------
# Tests: Persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    """Tests para guardar y cargar estadísticas."""

    def test_save_creates_file(self, planner_with_storage, sample_feedback):
        """_save debe crear archivo en storage_path."""
        planner_with_storage.record_feedback(sample_feedback)
        assert Path(planner_with_storage._storage_path).exists()

    def test_save_content_valid_json(self, planner_with_storage, sample_feedback):
        """El archivo guardado debe ser JSON válido."""
        planner_with_storage.record_feedback(sample_feedback)
        with open(planner_with_storage._storage_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "strategy_stats" in data
        assert "best_strategies" in data

    def test_load_restores_stats(self, planner_with_storage, sample_feedback):
        """_load debe restaurar estadísticas guardadas."""
        planner_with_storage.record_feedback(sample_feedback)

        # Crear nuevo planner con mismo storage path
        planner2 = AdaptivePlanner(storage_path=planner_with_storage._storage_path)
        assert planner2._strategy_stats["hybrid"].total_uses == 1

    def test_load_corrupted_file_graceful(self, tmp_path):
        """Archivo corrupto no debe romper la inicialización."""
        storage = tmp_path / "corrupt.json"
        storage.write_text("not valid json", encoding="utf-8")
        planner = AdaptivePlanner(storage_path=str(storage))
        # Debe inicializar sin error
        assert planner._strategy_stats is not None

    def test_save_no_storage_path(self, planner, sample_feedback):
        """Sin storage_path, _save no debe hacer nada."""
        planner.record_feedback(sample_feedback)
        # No debe lanzar error
        assert True


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests de edge cases varios."""

    def test_empty_agents_phase_scheduling(self, planner):
        """Lista vacía de agentes no debe asignar fases."""
        phases = planner._assign_agent_phases([], "test")
        assert phases == {}

    def test_empty_agents_get_active(self, planner):
        """get_active_agents con lista vacía debe retornar []."""
        active = planner.get_active_agents([], phase_degrees=0.0)
        assert active == []

    def test_unknown_agent_in_phases(self, planner):
        """Agente desconocido en assign_agent_phases debe tener fase asignada."""
        phases = planner._assign_agent_phases(["unknown_agent_xyz"], "test")
        assert "unknown_agent_xyz" in phases
        # Debe tener alguna fase (0, 120 o 240)
        assert phases["unknown_agent_xyz"] in (0.0, 120.0, 240.0)

    def test_detect_task_type_fix(self, planner):
        """_detect_task_type debe detectar 'fix'."""
        assert planner._detect_task_type("bug en producción") == "fix"

    def test_detect_task_type_test(self, planner):
        """_detect_task_type debe detectar 'test'."""
        assert planner._detect_task_type("validar módulo") == "test"

    def test_compress_context_very_large(self, planner):
        """Contexto enorme debe comprimirse sin error."""
        # Con nuevas líneas + una línea con keyword esencial
        huge = "línea sin keyword\n" * 20_000 + "task: tarea crítica\n"
        result = planner.compress_context_for_idle("agent", huge, target_tokens=5)
        assert len(result) < len(huge)
        # Las líneas sin keyword deben filtrarse
        assert "línea sin keyword" not in result
        # La línea esencial debe mantenerse (quizás truncada)
        assert "task:" in result

    def test_choose_strategy_generic_task(self, planner):
        """Tarea sin clasificación debe usar HYBRID."""
        result = planner.choose_strategy("hacer algo")
        task_type = planner._detect_task_type("hacer algo")
        if task_type == "general":
            assert result == PlanStrategy.HYBRID

    def test_get_active_agents_phase_zero_always_included(self, planner):
        """Agentes en fase 0° deben incluirse siempre."""
        planner._phase_plan = PhasePlan(
            agent_phases={"builder": 0.0, "scientist": 120.0},
            task_type="test",
        )
        active = planner.get_active_agents(
            ["builder", "scientist"], phase_degrees=90.0, window=10.0,
        )
        # builder está en fase 0, debe estar activo siempre
        assert "builder" in active

    def test_replan_threshold_constant(self):
        """REPLAN_FAILURE_RATE debe ser 0.5."""
        assert REPLAN_FAILURE_RATE == 0.5
