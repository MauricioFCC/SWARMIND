"""
Tests for ConfidenceScorer — heuristic confidence evaluation of agent outputs.

Cubre: ConfidenceScore dataclass, signal evaluators, score_completion,
      score_debate_agreement, and integration with task_orchestrator.
"""

import pytest
from harness.orchestrator.confidence_scorer import (
    ConfidenceScorer,
    ConfidenceScore,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
)


# ===========================================================================
# ConfidenceScore data class
# ===========================================================================

class TestConfidenceScore:
    """Verify the ConfidenceScore dataclass properties."""

    def test_confidence_high_threshold(self):
        """Score >= 0.90 → level='high', should_stop=True."""
        cs = ConfidenceScore(score=0.95, reasoning="Alta confianza")
        assert cs.level == "high"
        assert cs.should_stop is True

    def test_confidence_medium_threshold(self):
        """Score 0.70-0.89 → level='medium', should_stop=False."""
        cs = ConfidenceScore(score=0.75, reasoning="Confianza media")
        assert cs.level == "medium"
        assert cs.should_stop is False

    def test_confidence_low_threshold(self):
        """Score < 0.70 → level='low', should_stop=False."""
        cs = ConfidenceScore(score=0.35, reasoning="Baja confianza")
        assert cs.level == "low"
        assert cs.should_stop is False

    def test_score_boundary_high(self):
        """Score exactly at medium/high boundary."""
        cs_high = ConfidenceScore(score=CONFIDENCE_HIGH)
        assert cs_high.level == "high"
        assert cs_high.should_stop is True

    def test_score_boundary_medium(self):
        """Score exactly at low/medium boundary."""
        cs_medium = ConfidenceScore(score=CONFIDENCE_MEDIUM)
        assert cs_medium.level == "medium"
        assert cs_medium.should_stop is False

    def test_confidence_level_property(self):
        """level property returns correct string for all ranges."""
        assert ConfidenceScore(score=1.00).level == "high"
        assert ConfidenceScore(score=CONFIDENCE_HIGH).level == "high"
        assert ConfidenceScore(score=0.80).level == "medium"
        assert ConfidenceScore(score=CONFIDENCE_MEDIUM).level == "medium"
        assert ConfidenceScore(score=0.50).level == "low"
        assert ConfidenceScore(score=CONFIDENCE_LOW).level == "low"
        assert ConfidenceScore(score=0.00).level == "low"

    def test_should_stop_high_confidence(self):
        """should_stop is True only for high confidence."""
        assert ConfidenceScore(score=0.99).should_stop is True
        assert ConfidenceScore(score=0.90).should_stop is True

    def test_should_stop_low_confidence(self):
        """should_stop is False for medium and low confidence."""
        assert ConfidenceScore(score=0.89).should_stop is False
        assert ConfidenceScore(score=0.70).should_stop is False
        assert ConfidenceScore(score=0.50).should_stop is False
        assert ConfidenceScore(score=0.00).should_stop is False

    def test_to_dict(self):
        """to_dict returns serializable dict."""
        cs = ConfidenceScore(
            score=0.95,
            reasoning="Alta confianza",
            signals={"length": 1.0, "hedging": 0.9},
        )
        d = cs.to_dict()
        assert d["score"] == 0.95
        assert d["level"] == "high"
        assert d["should_stop"] is True
        assert d["reasoning"] == "Alta confianza"
        assert d["signals"]["length"] == 1.0
        assert d["signals"]["hedging"] == 0.9


# ===========================================================================
# Signal evaluators
# ===========================================================================

class TestSignalLength:
    """Test _signal_length heuristic."""

    def setup_method(self):
        self.scorer = ConfidenceScorer()

    def test_signal_length_short(self):
        """Very short output relative to task → low score."""
        task = "Implementa una API REST completa con Rust, incluyendo autenticación, validación y documentación"
        result = "ok"
        score = self.scorer._signal_length(task, result)
        assert score < 0.5, f"Expected low score for short output, got {score}"

    def test_signal_length_long(self):
        """Very long output relative to task → low score (rambling)."""
        task = "Hola"
        result = " ".join(["palabra"] * 5000)
        score = self.scorer._signal_length(task, result)
        assert score < 0.5, f"Expected low score for rambling output, got {score}"

    def test_signal_length_good(self):
        """Output 2x-20x task length → high score (goldilocks zone)."""
        task = "Escribe un saludo"
        result = "¡Hola! Bienvenido a este programa. Espero que te sea de utilidad. Un cordial saludo."
        score = self.scorer._signal_length(task, result)
        assert score >= 0.80, f"Expected high score for good length, got {score}"

    def test_signal_length_empty_task(self):
        """Empty task → falls in goldilocks zone since ratio is ~2-3x."""
        score = self.scorer._signal_length("", "some result")
        # empty task = 1 token (estimate_tokens min), result ~2-3 tokens
        # ratio ~2-3x → goldilocks zone
        assert score > 0.5, f"Expected high score, got {score}"


class TestSignalHedging:
    """Test _signal_hedging heuristic."""

    def setup_method(self):
        self.scorer = ConfidenceScorer()

    def test_signal_hedging_detected(self):
        """Output with hedging language → lower score."""
        result = "I think this might be the solution, but I'm not sure. Perhaps we should try another approach."
        score = self.scorer._signal_hedging(result)
        assert score < 0.7, f"Expected low score for hedging, got {score}"

    def test_signal_hedging_not_detected(self):
        """Output without hedging → high score (1.0)."""
        result = "The solution is to implement the API with Rust and Actix-web. The authentication middleware goes here."
        score = self.scorer._signal_hedging(result)
        assert score == 1.0, f"Expected max score for no hedging, got {score}"

    def test_signal_hedging_empty(self):
        """Empty result → 0.0."""
        score = self.scorer._signal_hedging("")
        assert score == 0.0

    def test_signal_hedging_spanish(self):
        """Hedging in Spanish is also detected."""
        result = "Quizás deberíamos considerar otra opción. No estoy seguro de que esta sea la mejor alternativa."
        score = self.scorer._signal_hedging(result)
        assert score < 0.8, f"Expected lower score for Spanish hedging, got {score}"


class TestSignalSelfCorrection:
    """Test _signal_self_correction heuristic."""

    def setup_method(self):
        self.scorer = ConfidenceScorer()

    def test_signal_self_correction(self):
        """Output with self-correction → lower score."""
        result = "The answer is 42. Actually, wait, let me reconsider. The correct answer is 43."
        score = self.scorer._signal_self_correction(result)
        assert score < 0.8, f"Expected lower score for self-correction, got {score}"

    def test_signal_self_correction_not_detected(self):
        """Output without self-correction → high score (1.0)."""
        result = "The answer is 42. This is definitive and well-researched."
        score = self.scorer._signal_self_correction(result)
        assert score == 1.0, f"Expected max score for no self-correction, got {score}"


# ===========================================================================
# score_completion integration
# ===========================================================================

class TestScoreCompletion:
    """Test the full score_completion pipeline."""

    def setup_method(self):
        self.scorer = ConfidenceScorer()

    def test_score_completion_high_quality(self):
        """Well-structured output → high confidence."""
        task = "Implementa una función de ordenación"
        result = (
            "Aquí está la implementación del algoritmo de ordenación QuickSort:\n\n"
            "```rust\n"
            "fn quicksort(arr: &mut [i32]) {\n"
            "    if arr.len() <= 1 { return; }\n"
            "    let pivot = partition(arr);\n"
            "    quicksort(&mut arr[..pivot]);\n"
            "    quicksort(&mut arr[pivot + 1..]);\n"
            "}\n"
            "```\n\n"
            "Este algoritmo tiene complejidad O(n log n) promedio y O(n²) peor caso."
        )
        score = self.scorer.score_completion(task, result, agent="builder")
        # Should have decent confidence — no hedging, good length
        assert score.score >= 0.5, f"Expected decent score, got {score.score:.2f}: {score.reasoning}"
        assert "length" in score.signals
        assert "hedging" in score.signals
        assert "self_correction" in score.signals

    def test_score_completion_low_quality(self):
        """Hesitant, hedged output → low confidence."""
        task = "Implementa una función de ordenación"
        result = (
            "I think maybe we could try something like... "
            "I'm not sure but possibly a sorting algorithm. "
            "Perhaps QuickSort? But I'm not certain. "
            "Actually wait, maybe BubbleSort is simpler. "
            "I guess it depends on the requirements."
        )
        score = self.scorer.score_completion(task, result, agent="builder")
        # Hedging + self-correction should significantly lower score
        assert score.score < 0.7, f"Expected low score for hedging, got {score.score:.2f}: {score.reasoning}"

    def test_score_completion_empty(self):
        """Empty result → zero confidence."""
        score = self.scorer.score_completion("task", "", agent="builder")
        assert score.score == 0.0
        assert score.should_stop is False

    def test_score_completion_with_speed(self):
        """Fast generation with good output → high confidence."""
        task = "Escribe un saludo simple"
        result = "¡Hola! Bienvenido al sistema."
        score = self.scorer.score_completion(
            task, result, agent="builder", duration_ms=500,
        )
        assert "speed" in score.signals
        assert score.score >= 0.5

    def test_score_completion_with_slow_speed(self):
        """Very slow generation → penalized confidence."""
        task = "Escribe un saludo simple"
        result = "Hola."
        score = self.scorer.score_completion(
            task, result, agent="builder", duration_ms=30000,
        )
        assert score.signals.get("speed", 1.0) < 0.5


# ===========================================================================
# Debate agreement
# ===========================================================================

class TestDebateAgreement:
    """Test score_debate_agreement for multi-agent consensus."""

    def setup_method(self):
        self.scorer = ConfidenceScorer()

    def test_score_debate_agreement(self):
        """Multiple agents with similar output lengths → high agreement."""
        outputs = {
            "builder": "La solución es implementar QuickSort con pivote mediana-de-tres para evitar el peor caso O(n²).",
            "scientist": "Tras analizar los algoritmos de ordenación, recomiendo QuickSort con optimización de pivote.",
            "guardian": "QuickSort con mediana-de-tres ha sido verificado. Todos los tests pasan correctamente.",
        }
        score = self.scorer.score_debate_agreement(outputs)
        assert score.score >= 0.5, f"Expected decent agreement, got {score.score:.2f}"
        assert "agreement" in score.signals

    def test_score_debate_agreement_single_agent(self):
        """Only one agent → default 0.5."""
        outputs = {"builder": "some output"}
        score = self.scorer.score_debate_agreement(outputs)
        assert score.score == 0.5

    def test_score_debate_agreement_disagreement(self):
        """Very different output lengths → lower agreement."""
        outputs = {
            "builder": "ok",
            "scientist": "Análisis exhaustivo de múltiples alternativas con ventajas y desventajas de cada enfoque posible.",
        }
        score = self.scorer.score_debate_agreement(outputs)
        # Very different lengths should give lower agreement
        assert score.score <= 0.7

    def test_score_debate_agreement_empty(self):
        """Empty outputs → low confidence."""
        outputs = {}
        score = self.scorer.score_debate_agreement(outputs)
        assert score.score == 0.5


# ===========================================================================
# Integration with task_planner SubTask.confidence_impact
# ===========================================================================

class TestConfidenceImpactInPlanner:
    """Verify that task_planner templates include confidence_impact."""

    def test_subtask_confidence_impact_default(self):
        """SubTask defaults to 'neutral'."""
        from harness.orchestrator.task_planner import SubTask
        st = SubTask(id="st-1", agent="builder", description="test")
        assert st.confidence_impact == "neutral"
        d = st.to_dict()
        assert d["confidence_impact"] == "neutral"

    def test_implement_api_has_critical(self):
        """implement_api builder subtask is critical."""
        from harness.orchestrator.task_planner import SUBTASK_TEMPLATES
        tpl = SUBTASK_TEMPLATES["implement_api"]
        assert tpl["subtasks"][0]["confidence_impact"] == "critical"

    def test_implement_api_has_validation(self):
        """implement_api security review is validation."""
        from harness.orchestrator.task_planner import SUBTASK_TEMPLATES
        tpl = SUBTASK_TEMPLATES["implement_api"]
        assert tpl["subtasks"][3]["confidence_impact"] == "validation"

    def test_general_has_validation(self):
        """general template has validation subtask (guardian tests)."""
        from harness.orchestrator.task_planner import SUBTASK_TEMPLATES
        tpl = SUBTASK_TEMPLATES["general"]
        # Index 3 is guardian tests/docs with validation impact
        validation_subtasks = [s for s in tpl["subtasks"] if s.get("confidence_impact") == "validation"]
        assert len(validation_subtasks) >= 1

    def test_planner_propagates_confidence_impact(self):
        """TaskPlanner.decompose() propagates confidence_impact to SubTask."""
        from harness.orchestrator.task_planner import TaskPlanner
        planner = TaskPlanner()
        plan = planner.decompose("implementa una API REST en Rust")
        # First subtask should be critical (builder)
        assert plan.subtasks[0].confidence_impact == "critical"
        # Security review should be validation
        validation_st = [s for s in plan.subtasks if s.confidence_impact == "validation"]
        assert len(validation_st) >= 1


# ===========================================================================
# Integration with task_orchestrator (confidence logging in process_completion)
# ===========================================================================

class TestConfidenceInOrchestrator:
    """Verify that process_completion logs confidence scores."""

    def test_process_completion_logs_confidence(self, caplog):
        """After completing a subtask, confidence is evaluated and logged."""
        from harness.orchestrator.task_orchestrator import TaskOrchestrator
        orch = TaskOrchestrator()

        result = orch.process_message("implementar API")
        first_id = result.current_level[0]["id"]

        import logging
        caplog.set_level(logging.INFO)

        next_result = orch.process_completion(
            session_id=result.session_id,
            subtask_id=first_id,
            result="API implementada correctamente con Rust y Actix-web. "
                   "Endpoints: GET /users, POST /users, DELETE /users. "
                   "Validación con serde, autenticación JWT.",
        )
        assert next_result is not None

        # Check that confidence evaluation was logged
        confidence_logged = any(
            "confidence_score" in record.message
            for record in caplog.records
        )
        assert confidence_logged, (
            "Expected confidence_score log entry in process_completion"
        )
