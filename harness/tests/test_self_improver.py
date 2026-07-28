"""
Tests para self_improver — SelfImprover, ImprovementRound, SkillImprovementStatus.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from harness.evolve_loop.cognition_sync import CognitionLesson, CognitionSync
from harness.evolve_loop.evaluator import CASEEvaluator, CASEValuation, FullEvaluation
from harness.evolve_loop.self_improver import (
    ImprovementRound,
    SelfImprover,
    SkillImprovementStatus,
)
from harness.tests.mock_vector_store import MockVectorStore

# ---------------------------------------------------------------------------
# Fixtures modulares
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cognition():
    """CognitionSync con MockVectorStore (evita LanceDB)."""
    store = MockVectorStore()
    store.create_collection("asi_cognition_store")
    return CognitionSync(vector_store=store)


@pytest.fixture
def improver(mock_cognition):
    """SelfImprover con cognition mockeada."""
    evaluator = CASEEvaluator()
    return SelfImprover(evaluator=evaluator, cognition=mock_cognition)


@pytest.fixture
def improver_no_cognition():
    """SelfImprover con cognition mockeada (no toca LanceDB)."""
    evaluator = CASEEvaluator()
    cognition = MagicMock()
    cognition.add_lesson.return_value = CognitionLesson(
        id="mock-id", title="mock", content="", domain="mock"
    )
    return SelfImprover(evaluator=evaluator, cognition=cognition)


# ===================================================================
# ImprovementRound
# ===================================================================


class TestImprovementRound:
    """Tests para el dataclass ImprovementRound."""

    def test_create(self):
        """Test creacion basica."""
        eval_ = FullEvaluation(
            clarify=CASEValuation("clarify", 0.8, ""),
            architect=CASEValuation("architect", 0.6, ""),
            solve=CASEValuation("solve", 0.9, ""),
            evaluate=CASEValuation("evaluate", 0.4, ""),
            overall=0.675,
        )
        lesson = CognitionLesson(id="l1", title="lesson", content="", domain="test")
        ir = ImprovementRound(
            round_number=1,
            skill_name="quant-dev",
            input_response="input",
            output_response="output",
            evaluation=eval_,
            score_delta=0.1,
            lesson=lesson,
        )
        assert ir.round_number == 1
        assert ir.skill_name == "quant-dev"
        assert ir.score_delta == 0.1
        assert ir.timestamp != ""
        assert ir.lesson is not None
        assert ir.lesson.id == "l1"


# ===================================================================
# SkillImprovementStatus
# ===================================================================


class TestSkillImprovementStatus:
    """Tests para el dataclass SkillImprovementStatus."""

    def test_create(self):
        """Test creacion basica."""
        status = SkillImprovementStatus(
            skill_name="test-skill",
            total_rounds=3,
            best_score=0.85,
            current_score=0.82,
            last_round_timestamp="2026-07-28T00:00:00",
            snapshot_history=["snap_a", "snap_b"],
        )
        assert status.skill_name == "test-skill"
        assert status.total_rounds == 3
        assert status.best_score == 0.85
        assert status.snapshot_history == ["snap_a", "snap_b"]


# ===================================================================
# SelfImprover — Init
# ===================================================================


class TestSelfImproverInit:
    """Tests de inicializacion de SelfImprover."""

    def test_init_with_dependencies(self):
        """Test init con evaluator y cognition inyectados."""
        evaluator = CASEEvaluator()
        cognition = CognitionSync(vector_store=MockVectorStore())
        improver = SelfImprover(evaluator=evaluator, cognition=cognition)
        assert improver.evaluator is evaluator
        assert improver.cognition is cognition
        assert improver._rounds == {}
        assert improver._promoted == {}

    def test_init_defaults_lance_fallback(self):
        """Test init sin argumentos usa dependencias por defecto (parchea LanceDB)."""
        with patch("harness.evolve_loop.cognition_sync.LanceVectorStore") as mock_lvs:
            mock_lvs.return_value = MockVectorStore()
            improver = SelfImprover()
            assert isinstance(improver.evaluator, CASEEvaluator)
            assert isinstance(improver.cognition, CognitionSync)


# ===================================================================
# SelfImprover — Run Round
# ===================================================================


class TestSelfImproverRunRound:
    """Tests para run_round."""

    def test_run_round_returns_list(self, improver):
        """Test run_round retorna lista de ImprovementRound."""
        rounds = improver.run_round("test-skill", rounds=1)
        assert len(rounds) == 1
        assert isinstance(rounds[0], ImprovementRound)
        assert rounds[0].skill_name == "test-skill"

    def test_run_round_multiple(self, improver):
        """Test run_round ejecuta N rondas correctamente."""
        rounds = improver.run_round("multi-skill", rounds=3)
        assert len(rounds) == 3
        assert rounds[0].round_number == 1
        assert rounds[1].round_number == 2
        assert rounds[2].round_number == 3

    def test_run_round_with_input_text(self, improver):
        """Test run_round acepta input_text personalizado."""
        custom_input = "This is a custom input with architecture, design, and code."
        rounds = improver.run_round("custom", rounds=1, input_text=custom_input)
        assert rounds[0].input_response == custom_input
        assert rounds[0].output_response.startswith(custom_input)

    def test_run_round_tracks_best_score(self, improver):
        """Test run_round actualiza best_score cuando hay mejora."""
        low_input = "ok"
        improver.run_round("track-best", rounds=1, input_text=low_input)
        best_after_r1 = improver._best_scores.get("track-best", 0.0)

        high_input = (
            "architecture design implement code trade-off risk "
            "clarify requirement stakeholder scope"
        )
        improver.run_round("track-best", rounds=1, input_text=high_input)
        best_after_r2 = improver._best_scores["track-best"]

        assert best_after_r2 >= best_after_r1

    def test_run_round_creates_snapshot_on_improvement(self, improver):
        """Test run_round crea snapshot cuando hay nuevo best score."""
        improver.run_round("snap-test", rounds=1)
        assert "snap-test" in improver._current_snapshots
        assert improver._current_snapshots["snap-test"] != ""

    def test_run_round_logs_lesson(self, improver):
        """Test run_round persiste leccion en cognition store."""
        improver.run_round("lesson-test", rounds=1)
        lessons = improver.cognition.search_lessons("C.A.S.E.", top_k=50)
        assert any("lesson-test" in l.title for l in lessons)


# ===================================================================
# SelfImprover — Promote
# ===================================================================


class TestSelfImproverPromote:
    """Tests para promote_best_snapshot."""

    def test_promote_no_snapshot(self, improver_no_cognition):
        """Test promote_best_snapshot retorna None sin rondas previas."""
        result = improver_no_cognition.promote_best_snapshot("never-run")
        assert result is None

    def test_promote_after_round(self, improver):
        """Test promote_best_snapshot retorna snapshot id tras ronda."""
        improver.run_round("promote-me", rounds=1)
        snapshot_id = improver.promote_best_snapshot("promote-me")
        assert snapshot_id is not None
        assert snapshot_id.startswith("snap_promote-me_")
        assert improver.has_been_promoted("promote-me") is True

    def test_promote_logs_lesson(self, improver):
        """Test promote_best_snapshot agrega leccion de promocion."""
        improver.run_round("promo-log", rounds=1)
        improver.promote_best_snapshot("promo-log")
        lessons = improver.cognition.search_lessons("Snapshot promoted", top_k=50)
        assert any("promo-log" in l.title for l in lessons)


# ===================================================================
# SelfImprover — Status / Query
# ===================================================================


class TestSelfImproverStatus:
    """Tests para metodos de consulta de estado."""

    def test_get_status_empty(self, improver_no_cognition):
        """Test get_status retorna [] sin rondas."""
        assert improver_no_cognition.get_status() == []

    def test_get_status_after_rounds(self, improver):
        """Test get_status retorna estado tras rondas."""
        improver.run_round("status-test", rounds=2)
        statuses = improver.get_status()
        assert len(statuses) == 1
        status = statuses[0]
        assert status.skill_name == "status-test"
        assert status.total_rounds == 2
        assert status.current_score >= 0

    def test_get_round_history(self, improver):
        """Test get_round_history retorna historial del skill."""
        improver.run_round("history-test", rounds=3)
        history = improver.get_round_history("history-test")
        assert len(history) == 3
        assert history[0].round_number == 1
        assert history[2].round_number == 3

    def test_get_round_history_empty(self, improver_no_cognition):
        """Test get_round_history retorna [] para skill sin rondas."""
        assert improver_no_cognition.get_round_history("unknown") == []

    def test_has_been_promoted_default_false(self, improver_no_cognition):
        """Test has_been_promoted retorna False sin promocion."""
        assert improver_no_cognition.has_been_promoted("any") is False


# ===================================================================
# SelfImprover — Metodos internos
# ===================================================================


class TestSelfImproverInternal:
    """Tests para metodos internos."""

    def test_generate_input_placeholder(self, improver_no_cognition):
        """Test _generate_input_placeholder genera texto con nombre y ronda."""
        text = improver_no_cognition._generate_input_placeholder("quant-dev", 1)
        assert "quant-dev" in text
        assert "round 1" in text
        assert "evaluate the trade-offs" in text

    def test_simulate_improvement_all_weak(self, improver_no_cognition):
        """Test _simulate_improvement agrega todas las mejoras si todas son debiles."""
        eval_ = FullEvaluation(
            clarify=CASEValuation("clarify", 0.1, "weak"),
            architect=CASEValuation("architect", 0.1, "weak"),
            solve=CASEValuation("solve", 0.1, "weak"),
            evaluate=CASEValuation("evaluate", 0.1, "weak"),
            overall=0.1,
        )
        result = improver_no_cognition._simulate_improvement("Input text", eval_, "test")
        assert "clarify" in result.lower()
        assert "architect" in result.lower()
        assert "concrete implementation" in result.lower()
        assert "trade-offs" in result.lower()

    def test_simulate_improvement_all_strong(self, improver_no_cognition):
        """Test _simulate_improvement usa mensaje generico si todo es fuerte."""
        eval_ = FullEvaluation(
            clarify=CASEValuation("clarify", 0.9, "strong"),
            architect=CASEValuation("architect", 0.9, "strong"),
            solve=CASEValuation("solve", 0.9, "strong"),
            evaluate=CASEValuation("evaluate", 0.9, "strong"),
            overall=0.9,
        )
        result = improver_no_cognition._simulate_improvement("Input", eval_, "test")
        assert "addressed the C.A.S.E. dimensions" in result

    def test_store_lesson(self, mock_cognition):
        """Test _store_lesson persiste y retorna CognitionLesson."""
        improver = SelfImprover(evaluator=CASEEvaluator(), cognition=mock_cognition)
        eval_ = FullEvaluation(
            clarify=CASEValuation("clarify", 0.8, ""),
            architect=CASEValuation("architect", 0.6, ""),
            solve=CASEValuation("solve", 0.9, ""),
            evaluate=CASEValuation("evaluate", 0.4, ""),
            overall=0.675,
        )
        lesson = improver._store_lesson("test-skill", 1, eval_)
        assert isinstance(lesson, CognitionLesson)
        assert lesson.title != ""
        assert lesson.domain == "self_improvement.test-skill"
        assert "self_improvement" in lesson.tags
        assert lesson.metrics["overall_score"] == 0.675
        assert lesson.metrics["case_clarify"] == 0.8
