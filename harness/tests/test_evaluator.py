"""
Tests para evaluator — CASEEvaluator, CASEValuation, FullEvaluation.
"""
from __future__ import annotations

import pytest

from harness.evolve_loop.evaluator import CASEEvaluator, CASEValuation, FullEvaluation

# ===================================================================
# CASEValuation
# ===================================================================


class TestCASEValuation:
    """Tests para el dataclass CASEValuation."""

    def test_create(self):
        """Test creacion basica con valores."""
        v = CASEValuation(
            dimension="clarify",
            score=0.75,
            feedback="Good clarifying response",
            matched_terms=["clarify", "what if"],
            term_count=2,
            total_markers=21,
        )
        assert v.dimension == "clarify"
        assert v.score == 0.75
        assert v.feedback == "Good clarifying response"


# ===================================================================
# FullEvaluation
# ===================================================================


class TestFullEvaluation:
    """Tests para el dataclass FullEvaluation."""

    @pytest.fixture
    def full_eval(self):
        """FullEvaluation de ejemplo."""
        return FullEvaluation(
            clarify=CASEValuation("clarify", 0.8, "Strong clarify", ["clarify"]),
            architect=CASEValuation("architect", 0.6, "Moderate architect", ["design"]),
            solve=CASEValuation("solve", 0.9, "Strong solve", ["code"]),
            evaluate=CASEValuation("evaluate", 0.4, "Weak evaluate", []),
            overall=0.675,
        )

    def test_to_dict(self, full_eval):
        """Test to_dict exporta estructura completa."""
        d = full_eval.to_dict()
        assert "clarify" in d
        assert "architect" in d
        assert "solve" in d
        assert "evaluate" in d
        assert d["overall"] == 0.675
        assert d["clarify"]["score"] == 0.8
        assert d["clarify"]["matched_terms"] == ["clarify"]
        assert d["evaluate"]["score"] == 0.4

    def test_overall_computation(self):
        """Test overall es el promedio de los 4 scores."""
        c = CASEValuation("clarify", 1.0, "")
        a = CASEValuation("architect", 0.5, "")
        s = CASEValuation("solve", 0.0, "")
        e = CASEValuation("evaluate", 0.5, "")
        fe = FullEvaluation(clarify=c, architect=a, solve=s, evaluate=e, overall=0.5)
        assert fe.overall == 0.5


# ===================================================================
# CASEEvaluator
# ===================================================================


class TestCASEEvaluatorInit:
    """Tests de inicializacion de CASEEvaluator."""

    def test_init(self):
        """Test init crea listas de markers."""
        ev = CASEEvaluator()
        assert len(ev._clarify_markers) > 0
        assert len(ev._architect_markers) > 0
        assert len(ev._solve_markers) > 0
        assert len(ev._evaluate_markers) > 0


class TestCASEEvaluatorClarify:
    """Tests para evaluate_clarify."""

    def test_clarify_high_score(self):
        """Test respuesta con marcadores de clarify obtiene score proporcionado."""
        ev = CASEEvaluator()
        text = (
            "What do you mean by that? Let me understand the problem. "
            "Could you clarify the requirements? What is the goal? "
            "I need more context about the stakeholder expectations. "
            "What if we consider who is affected and why is this needed? "
            "Let me break this down to define the problem scope."
        )
        result = ev.evaluate_clarify(text)
        assert result.score > 0
        assert result.dimension == "clarify"
        assert len(result.matched_terms) > 0
        assert result.total_markers == 21  # total de markers en _CLARIFY_MARKERS

    def test_clarify_low_score(self):
        """Test respuesta sin marcadores de clarify obtiene score bajo."""
        ev = CASEEvaluator()
        text = "Here is the code. It implements the solution."
        result = ev.evaluate_clarify(text)
        assert result.score < 0.2
        assert result.matched_terms == []


class TestCASEEvaluatorArchitect:
    """Tests para evaluate_architect."""

    def test_architect_high_score(self):
        """Test respuesta con marcadores de architecture obtiene score proporcionado."""
        ev = CASEEvaluator()
        text = (
            "The architecture uses hexagonal design with ports and adapters. "
            "The system will have clear layers and separation of concerns. "
            "I propose a component diagram showing the data flow. "
            "The high-level model uses a service layer with API endpoints "
            "and dependency injection for the pipeline structure."
        )
        result = ev.evaluate_architect(text)
        assert result.score > 0
        assert result.dimension == "architect"
        assert result.total_markers == 30

    def test_architect_no_match(self):
        """Test respuesta sin marcadores de arquitectura."""
        ev = CASEEvaluator()
        text = "Just fix the bug quickly."
        result = ev.evaluate_architect(text)
        assert result.score < 0.1


class TestCASEEvaluatorSolve:
    """Tests para evaluate_solve."""

    def test_solve_high_score(self):
        """Test respuesta con marcadores de implementacion obtiene score proporcionado."""
        ev = CASEEvaluator()
        text = (
            "Let me implement the function. First, I will write the class "
            "and method. Here is the code snippet. Then run the tests "
            "to verify the build compiles correctly. I will optimize the "
            "setup and deploy the config changes."
        )
        result = ev.evaluate_solve(text)
        assert result.score > 0
        assert result.dimension == "solve"
        assert result.total_markers == 32

    def test_solve_empty(self):
        """Test cadena vacia produce score 0."""
        ev = CASEEvaluator()
        result = ev.evaluate_solve("")
        assert result.score == 0.0


class TestCASEEvaluatorEvaluate:
    """Tests para evaluate_evaluate."""

    def test_evaluate_high_score(self):
        """Test respuesta con marcadores de evaluacion obtiene score proporcionado."""
        ev = CASEEvaluator()
        text = (
            "However, there are trade-offs to consider. The main risk is "
            "scalability. On the other hand, the performance improves. "
            "Let me compare alternatives and assess the complexity cost. "
            "I recommend a review of the limitations and edge cases. "
            "The testing strategy should cover the failure modes."
        )
        result = ev.evaluate_evaluate(text)
        assert result.score > 0
        assert result.dimension == "evaluate"
        assert result.total_markers == 34

    def test_evaluate_no_terms(self):
        """Test respuesta tecnica sin evaluacion."""
        ev = CASEEvaluator()
        text = "Run the script. It works."
        result = ev.evaluate_evaluate(text)
        assert result.score < 0.2


class TestCASEEvaluatorFull:
    """Tests para evaluate_full."""

    def test_evaluate_full_returns_all_dimensions(self):
        """Test evaluate_full retorna las 4 dimensiones C.A.S.E."""
        ev = CASEEvaluator()
        text = (
            "Let me clarify the requirements. The architecture uses "
            "hexagonal design. I will implement the solution in Python. "
            "However, there are trade-offs with performance."
        )
        result = ev.evaluate_full(text)
        assert isinstance(result, FullEvaluation)
        assert result.clarify.score >= 0
        assert result.architect.score >= 0
        assert result.solve.score >= 0
        assert result.evaluate.score >= 0
        assert 0 <= result.overall <= 1.0

    def test_evaluate_full_empty_string(self):
        """Test evaluate_full con cadena vacia produce scores 0."""
        ev = CASEEvaluator()
        result = ev.evaluate_full("")
        assert result.overall == 0.0
        assert result.clarify.score == 0.0
        assert result.architect.score == 0.0
        assert result.solve.score == 0.0
        assert result.evaluate.score == 0.0

    def test_evaluate_full_overall_average(self):
        """Test overall es el promedio exacto de las 4 dimensiones."""
        ev = CASEEvaluator()
        text = "architecture design implement code trade-off risk"
        result = ev.evaluate_full(text)
        expected = (
            result.clarify.score
            + result.architect.score
            + result.solve.score
            + result.evaluate.score
        ) / 4.0
        assert abs(result.overall - expected) < 1e-6


class TestCASEEvaluatorDimensionFeedback:
    """Tests para _dimension_feedback."""

    def test_feedback_strong(self):
        """Test feedback para score >= 0.50 es 'Strong'."""
        fb = CASEEvaluator._dimension_feedback("clarify", 0.75, 10)
        assert "Strong clarify" in fb
        assert "10 markers" in fb

    def test_feedback_moderate(self):
        """Test feedback para 0.20 <= score < 0.50 es 'Moderate'."""
        fb = CASEEvaluator._dimension_feedback("architect", 0.35, 4)
        assert "Moderate architect" in fb
        assert "4 markers" in fb

    def test_feedback_weak(self):
        """Test feedback para score < 0.20 es 'Weak'."""
        fb = CASEEvaluator._dimension_feedback("solve", 0.05, 1)
        assert "Weak solve" in fb
        assert "1 markers" in fb
