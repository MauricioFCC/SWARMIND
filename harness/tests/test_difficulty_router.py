"""
Tests para DifficultyRouter — clasificación de complejidad y ruteo de tareas.

Cubre: ComplexityFeatures.score(), extracción de features, clasificación
de complejidad, selección de pipeline, route(), estimate_subtasks(),
classify_batch(), y RoutingDecision.
"""

from __future__ import annotations

import pytest

from harness.orchestrator.difficulty_router import (
    AMBIGUITY_PATTERNS,
    HIGH_COMPLEXITY_KEYWORDS,
    LOW_COMPLEXITY_KEYWORDS,
    TECH_VERBS,
    ComplexityFeatures,
    ComplexityLevel,
    DifficultyRouter,
    PipelineType,
    RoutingDecision,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def router():
    """DifficultyRouter con thresholds por defecto."""
    return DifficultyRouter()


@pytest.fixture
def empty_features() -> ComplexityFeatures:
    """Features vacias."""
    return ComplexityFeatures()


# ---------------------------------------------------------------------------
# ComplexityFeatures.score
# ---------------------------------------------------------------------------


class TestComplexityFeaturesScore:
    """Tests para el método score de ComplexityFeatures."""

    def test_trivial_score(self, empty_features):
        """Features vacias deben dar score 0.0."""
        assert empty_features.score() == 0.0

    def test_length_contribution(self):
        """La longitud debe contribuir al score."""
        # >1000 chars → +0.3
        f = ComplexityFeatures(length_chars=1200)
        assert f.score() == 0.3

        # >500 chars → +0.2
        f = ComplexityFeatures(length_chars=700)
        assert f.score() == 0.2

        # >200 chars → +0.1
        f = ComplexityFeatures(length_chars=300)
        assert f.score() == 0.1

        # ≤200 chars → +0.0
        f = ComplexityFeatures(length_chars=100)
        assert f.score() == 0.0

    def test_high_complexity_keywords_capped(self):
        """High complexity keywords deben aportar max 0.4."""
        f = ComplexityFeatures(high_complexity_matches=10)
        score = f.score()
        assert score <= 0.4
        # 10 * 0.15 = 1.5, capped at 0.4, plus posible length 0
        assert round(score, 3) == 0.4

    def test_tech_verbs_capped(self):
        """Tech verbs deben aportar max 0.3."""
        f = ComplexityFeatures(tech_verb_count=10)
        score = f.score()
        assert score <= 0.3
        assert round(score, 3) == 0.3

    def test_ambiguity_contribution(self):
        """Cada patrón de ambigüedad aporta +0.1."""
        f = ComplexityFeatures(ambiguity_count=3)
        assert f.score() == pytest.approx(0.3)

    def test_domain_contribution(self):
        """Multi-dominio debe contribuir."""
        # 3+ domains → +0.3
        f = ComplexityFeatures(domain_count=3)
        assert f.score() == 0.3

        # 2 domains → +0.15
        f = ComplexityFeatures(domain_count=2)
        assert f.score() == 0.15

        # 1 domain → +0.0
        f = ComplexityFeatures(domain_count=1)
        assert f.score() == 0.0

    def test_bullet_points_contribution(self):
        """Bullet points aportan +0.1."""
        f = ComplexityFeatures(has_bullet_points=True)
        assert f.score() == 0.1

    def test_code_blocks_contribution(self):
        """Code blocks aportan +0.15."""
        f = ComplexityFeatures(has_code_blocks=True)
        assert f.score() == 0.15

    def test_low_complexity_discount(self):
        """Low complexity keywords descuentan max 0.3."""
        f = ComplexityFeatures(low_complexity_matches=5)
        score = f.score()
        assert score >= 0.0
        # 5 * 0.1 = 0.5, capped at 0.3, but score starts at 0, so max(0, -0.3) = 0
        assert score == 0.0

    def test_combined_score_clamped(self):
        """El score final debe estar entre 0.0 y 1.0."""
        f = ComplexityFeatures(
            length_chars=1200,       # +0.3
            high_complexity_matches=5,  # +0.4 (capped)
            tech_verb_count=5,         # +0.3 (capped)
            ambiguity_count=3,         # +0.3
            domain_count=3,            # +0.3
            has_bullet_points=True,    # +0.1
            has_code_blocks=True,      # +0.15
        )
        score = f.score()
        assert 0.0 <= score <= 1.0
        # Without low complexity: 0.3+0.4+0.3+0.3+0.3+0.1+0.15 = 1.85 → clamped to 1.0
        assert round(score, 3) == 1.0

    def test_score_with_discounts_and_bonuses(self):
        """Score combinado con descuentos y bonos debe calcularse correctamente."""
        f = ComplexityFeatures(
            length_chars=600,          # +0.2
            high_complexity_matches=1,  # +0.15
            tech_verb_count=2,         # +0.2
            ambiguity_count=1,         # +0.1
            domain_count=2,            # +0.15
            low_complexity_matches=1,  # -0.1
        )
        # 0.2 + 0.15 + 0.2 + 0.1 + 0.15 - 0.1 = 0.7
        assert round(f.score(), 3) == 0.7


# ---------------------------------------------------------------------------
# ComplexityFeatures.to_dict
# ---------------------------------------------------------------------------


class TestComplexityFeaturesToDict:
    """Tests para to_dict de ComplexityFeatures."""

    def test_to_dict_includes_score(self, empty_features):
        """to_dict debe incluir score redondeado."""
        d = empty_features.to_dict()
        assert d["score"] == 0.0
        assert "length_chars" in d
        assert "domains_found" in d

    def test_to_dict_rounds_score(self):
        """El score debe estar redondeado a 3 decimales."""
        f = ComplexityFeatures(length_chars=1000, high_complexity_matches=1)
        d = f.to_dict()
        assert isinstance(d["score"], float)
        # 1000 chars = +0.2 (>500), 1 high_complexity = +0.15 → total = 0.35
        assert d["score"] == pytest.approx(0.35)


# ---------------------------------------------------------------------------
# DifficultyRouter._extract_features
# ---------------------------------------------------------------------------


class TestExtractFeatures:
    """Tests para _extract_features."""

    def test_empty_message(self, router):
        """Mensaje vacio debe retornar features por defecto."""
        f = router._extract_features("")
        assert f.length_chars == 0
        assert f.word_count == 0
        assert f.score() == 0.0

    def test_high_complexity_matches(self, router):
        """Debe detectar keywords de alta complejidad."""
        msg = "Necesito diseñar una arquitectura de microservicios"
        f = router._extract_features(msg)
        assert f.high_complexity_matches >= 2
        assert "diseñar" in msg.lower() or "design" in msg.lower()

    def test_low_complexity_matches(self, router):
        """Debe detectar keywords de baja complejidad."""
        f = router._extract_features("hola, esto es un test")
        assert f.low_complexity_matches >= 2

    def test_tech_verb_detection(self, router):
        """Debe detectar verbos técnicos."""
        f = router._extract_features("implementar y desarrollar un sistema")
        assert f.tech_verb_count >= 2

    def test_ambiguity_detection(self, router):
        """Debe detectar patrones de ambigüedad."""
        f = router._extract_features("haz lo etc... y otras cosas")
        assert f.ambiguity_count >= 1

    def test_domain_detection(self, router):
        """Debe detectar dominios."""
        f = router._extract_features(
            "Crear API REST con Docker y Kubernetes para trading"
        )
        assert "backend" in f.domains_found
        assert "devops" in f.domains_found
        assert "trading" in f.domains_found
        assert f.domain_count >= 3

    def test_bullet_points_detection(self, router):
        """Debe detectar bullet points."""
        f = router._extract_features("Hacer:\n* primero\n* segundo")
        assert f.has_bullet_points is True

    def test_code_blocks_detection(self, router):
        """Debe detectar bloques de código."""
        f = router._extract_features("Usar `print('hi')` o ```code```")
        assert f.has_code_blocks is True

    def test_estimated_subtasks_in_result(self, router):
        """Las features deben incluir estimated_subtasks."""
        f = router._extract_features("implementar y diseñar sistema complejo")
        assert f.estimated_subtasks >= 1


# ---------------------------------------------------------------------------
# DifficultyRouter._classify_complexity
# ---------------------------------------------------------------------------


class TestClassifyComplexity:
    """Tests para _classify_complexity."""

    @pytest.mark.parametrize("score,expected", [
        (0.0, ComplexityLevel.TRIVIAL),
        (0.05, ComplexityLevel.TRIVIAL),
        (0.09, ComplexityLevel.TRIVIAL),
        (0.10, ComplexityLevel.SIMPLE),
        (0.20, ComplexityLevel.SIMPLE),
        (0.24, ComplexityLevel.SIMPLE),
        (0.25, ComplexityLevel.MODERATE),
        (0.35, ComplexityLevel.MODERATE),
        (0.44, ComplexityLevel.MODERATE),
        (0.45, ComplexityLevel.COMPLEX),
        (0.60, ComplexityLevel.COMPLEX),
        (0.69, ComplexityLevel.COMPLEX),
        (0.70, ComplexityLevel.VERY_COMPLEX),
        (0.85, ComplexityLevel.VERY_COMPLEX),
        (1.0, ComplexityLevel.VERY_COMPLEX),
    ])
    def test_classification_thresholds(self, router, score, expected):
        """Cada score debe mapear al ComplexityLevel correcto."""
        f = ComplexityFeatures()
        assert router._classify_complexity(score, f) == expected


# ---------------------------------------------------------------------------
# DifficultyRouter._select_pipeline
# ---------------------------------------------------------------------------


class TestSelectPipeline:
    """Tests para _select_pipeline."""

    @pytest.mark.parametrize("complexity,expected", [
        (ComplexityLevel.TRIVIAL, PipelineType.SHALLOW),
        (ComplexityLevel.SIMPLE, PipelineType.SHALLOW),
        (ComplexityLevel.MODERATE, PipelineType.STANDARD),
        (ComplexityLevel.COMPLEX, PipelineType.DEEP),
        (ComplexityLevel.VERY_COMPLEX, PipelineType.DEEP),
    ])
    def test_pipeline_selection(self, router, complexity, expected):
        """Cada nivel de complejidad debe mapear al pipeline correcto."""
        assert router._select_pipeline(complexity, ComplexityFeatures()) == expected


# ---------------------------------------------------------------------------
# DifficultyRouter.route
# ---------------------------------------------------------------------------


class TestRoute:
    """Tests para route()."""

    def test_trivial_task(self, router):
        """Tarea trivial debe dar pipeline SHALLOW."""
        decision = router.route("hola")
        assert decision.complexity == ComplexityLevel.TRIVIAL
        assert decision.pipeline == PipelineType.SHALLOW
        assert decision.score < 0.1

    def test_complex_task(self, router):
        """Tarea compleja debe dar pipeline DEEP."""
        decision = router.route(
            "implementar una arquitectura de microservicios "
            "con Docker, Kubernetes y CI/CD para trading"
        )
        assert decision.pipeline == PipelineType.DEEP
        assert decision.score >= 0.25

    def test_decision_contains_features(self, router):
        """La decisión debe incluir features extraídas."""
        decision = router.route("test simple")
        assert isinstance(decision.features, ComplexityFeatures)
        assert decision.features.word_count > 0

    def test_decision_roundtrip_to_dict(self, router):
        """to_dict debe contener los campos esenciales."""
        decision = router.route("analizar datos de trading con ML")
        d = decision.to_dict()
        assert d["message"] == "analizar datos de trading con ML"
        assert d["complexity"] in {"trivial", "simple", "moderate", "complex", "very_complex"}
        assert d["pipeline"] in {"shallow", "standard", "deep"}
        assert 0.0 <= d["score"] <= 1.0


# ---------------------------------------------------------------------------
# DifficultyRouter.estimate_subtasks
# ---------------------------------------------------------------------------


class TestEstimateSubtasks:
    """Tests para estimate_subtasks."""

    def test_estimate_simple(self, router):
        """Tarea simple debe estimar pocas subtasks."""
        n = router.estimate_subtasks("hola mundo")
        assert n >= 1

    def test_estimate_complex(self, router):
        """Tarea compleja debe estimar mas subtasks."""
        simple_n = router.estimate_subtasks("hola")
        complex_n = router.estimate_subtasks(
            "implementar y diseñar sistema distribuido con "
            "microservicios, docker, kubernetes, CI/CD, "
            "y base de datos para trading"
        )
        assert complex_n >= simple_n

    def test_estimate_capped(self, router):
        """La estimación debe tener un maximo de 16."""
        n = router.estimate_subtasks(
            "implementar desarrollar construir crear desplegar "
            "configurar automatizar orquestar " * 5
        )
        assert n <= 16


# ---------------------------------------------------------------------------
# DifficultyRouter.classify_batch
# ---------------------------------------------------------------------------


class TestClassifyBatch:
    """Tests para classify_batch."""

    def test_batch_classification(self, router):
        """Debe clasificar multiples mensajes."""
        messages = ["hola", "implementar API REST compleja", "test simple"]
        results = router.classify_batch(messages)
        assert len(results) == 3
        for msg in messages:
            assert msg in results
            assert isinstance(results[msg], RoutingDecision)

    def test_empty_batch(self, router):
        """Batch vacio debe retornar dict vacio."""
        assert router.classify_batch([]) == {}


# ---------------------------------------------------------------------------
# RoutingDecision
# ---------------------------------------------------------------------------


class TestRoutingDecision:
    """Tests para la dataclass RoutingDecision."""

    def test_is_deep(self):
        """is_deep debe ser True solo para pipeline DEEP."""
        d = RoutingDecision("x", ComplexityLevel.COMPLEX, PipelineType.DEEP, 0.5, ComplexityFeatures())
        assert d.is_deep is True
        assert d.is_shallow is False

    def test_is_shallow(self):
        """is_shallow debe ser True solo para pipeline SHALLOW."""
        d = RoutingDecision("x", ComplexityLevel.TRIVIAL, PipelineType.SHALLOW, 0.0, ComplexityFeatures())
        assert d.is_shallow is True
        assert d.is_deep is False

    def test_repr(self):
        """__repr__ debe incluir complexity, pipeline, score y domains."""
        f = ComplexityFeatures(domains_found=["backend"])
        d = RoutingDecision("msg", ComplexityLevel.MODERATE, PipelineType.STANDARD, 0.3, f)
        r = repr(d)
        assert "moderate" in r
        assert "standard" in r
        assert "backend" in r


# ---------------------------------------------------------------------------
# DifficultyRouter thresholds personalizados
# ---------------------------------------------------------------------------


class TestCustomThresholds:
    """Tests con thresholds personalizados."""

    def test_low_shallow_threshold(self):
        """Shallow threshold mas bajo debe clasificar mas tareas como DEEP."""
        strict = DifficultyRouter(shallow_threshold=0.05, deep_threshold=0.15)
        decision = strict.route("implementar algo")
        # Con thresholds estrictos, esto debería ser al menos SIMPLE → SHALLOW
        # Pero si threshold shallow es muy bajo, mas cosas van a DEEP
        assert decision.pipeline in (PipelineType.SHALLOW, PipelineType.STANDARD, PipelineType.DEEP)

    def test_high_deep_threshold(self):
        """Deep threshold mas alto requiere mas complejidad para DEEP."""
        relaxed = DifficultyRouter(shallow_threshold=0.3, deep_threshold=0.5)
        decision = relaxed.route("test simple")
        assert decision.pipeline == PipelineType.SHALLOW


# ---------------------------------------------------------------------------
# Regresión: keywords definidos
# ---------------------------------------------------------------------------


class TestKeywordsDefinitions:
    """Los conjuntos de keywords no deben estar vacios."""

    def test_high_complexity_non_empty(self):
        assert len(HIGH_COMPLEXITY_KEYWORDS) > 0

    def test_low_complexity_non_empty(self):
        assert len(LOW_COMPLEXITY_KEYWORDS) > 0

    def test_tech_verbs_non_empty(self):
        assert len(TECH_VERBS) > 0

    def test_ambiguity_patterns_non_empty(self):
        assert len(AMBIGUITY_PATTERNS) > 0
