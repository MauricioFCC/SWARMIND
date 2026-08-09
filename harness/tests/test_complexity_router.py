"""Tests para ComplexityRouter — routing por complejidad semántica (H1, estilo RouteLLM).

Complementa a ModelRouter (router.py): mientras ModelRouter enruta por
dominio/longitud con fallback, ComplexityRouter estima la complejidad de la
tarea (0..100) con señales y decide entre modelo small y modelo frontier.

Cubre: scoring por señales, clamp [0, 100], umbral calibrable en caliente,
API corta route(), red de seguridad route_with_validation() (escala a
frontier si la validación del modelo small falla) y resumen legible.

Las longitudes de las tareas de prueba están verificadas para que las
señales de longitud sean aritméticamente exactas.
"""

import pytest

from harness.model_router.complexity_router import (
    ComplexityDecision,
    ComplexityRouter,
)

# ---------------------------------------------------------------------------
# Tareas de prueba (longitudes verificadas: len, commas)
# ---------------------------------------------------------------------------

# 136 chars, 4 comas -> keywords(+50) + multi_instruction(+10) = 60
REASONING_TASK = (
    "analiza y deriva la complejidad de este algoritmo, optimiza el "
    "rendimiento, justifica cada paso, evalúa el resultado, prueba la solución"
)

# 70 chars -> keywords(+50) = 50 (boundary con threshold 50)
BOUNDARY_TASK = "analiza y deriva la complejidad de este algoritmo recursivo en detalle"

# 191 chars -> keywords(+50) + domain_complex(+20) = 70
DOMAIN_TASK = (
    "analiza esta jurisprudencia legal sobre responsabilidad contractual, "
    "evalúa los precedentes citados, justifica la aplicación de cada norma "
    "y compara los criterios de los tribunales superiores"
)

# 3450 chars, 120 comas -> long_high(+30) + keywords(+50) + domain(+20)
# + multi(+10) = 110 -> clamp 100
CLAMP_HIGH_TASK = (
    "analiza la jurisprudencia legal, optimiza el diseño, justifica cada paso, "
    "evalúa el resultado, prueba la solución. " * 30
)

# 1680 chars, 0 comas -> long_high(+30) + simple_term(-20) = 10
SIMPLE_LONG_TASK = (
    "traduce este texto al inglés. "
    "lorem ipsum dolor sit amet consectetur adipiscing elit " * 30
)


class TestScoring:
    """Señales de complejidad y clamp del score."""

    def test_short_simple_task_routes_small(self):
        r = ComplexityRouter()
        decision = r.decide("lista los archivos")
        assert decision.route == "small"
        assert decision.score == 0.0

    def test_reasoning_task_routes_frontier(self):
        r = ComplexityRouter()
        decision = r.decide(REASONING_TASK)
        assert decision.route == "frontier"
        assert decision.score == 60.0

    def test_complex_domain_task_routes_frontier(self):
        r = ComplexityRouter()
        decision = r.decide(DOMAIN_TASK)
        assert decision.route == "frontier"
        assert "domain_complex" in decision.signals

    def test_simple_keyword_routes_small_even_when_long(self):
        """Aunque la tarea sea larga (+30), el término simple (-20) la mantiene small."""
        r = ComplexityRouter()
        decision = r.decide(SIMPLE_LONG_TASK)
        assert decision.route == "small"
        assert decision.score == 10.0

    def test_long_high_contributes_30(self):
        r = ComplexityRouter()
        decision = r.decide("x" * 900)
        assert decision.score == 30.0
        assert "long_high" in decision.signals

    def test_score_clamped_to_max_100(self):
        r = ComplexityRouter()
        decision = r.decide(CLAMP_HIGH_TASK)
        assert decision.score == 100.0
        assert decision.score <= 100.0

    def test_score_clamped_to_min_0(self):
        r = ComplexityRouter()
        decision = r.decide("lista los archivos")
        assert decision.score == 0.0
        assert decision.score >= 0.0

    def test_domain_signal_fires_without_reasoning(self):
        """El dominio complejo aporta señal aunque no haya keywords de razonamiento."""
        r = ComplexityRouter()
        decision = r.decide(
            "clasifica los documentos de esta investigación cuantitativa sobre seguridad"
        )
        assert "domain_complex" in decision.signals

    def test_signals_contain_activated_signals(self):
        r = ComplexityRouter()
        decision = r.decide("lista los archivos")
        assert set(decision.signals) == {"short_task", "simple_task_term"}


class TestDecide:
    """Umbral, boundary y razón."""

    def test_custom_threshold_80_routes_almost_everything_small(self):
        r = ComplexityRouter(threshold=80.0)
        assert r.decide(REASONING_TASK).route == "small"
        assert r.decide(CLAMP_HIGH_TASK).route == "frontier"

    def test_boundary_score_equals_threshold_routes_frontier(self):
        r = ComplexityRouter()
        decision = r.decide(BOUNDARY_TASK)
        assert decision.score == 50.0
        assert decision.route == "frontier"

    def test_reason_contains_score(self):
        r = ComplexityRouter()
        decision = r.decide("lista los archivos")
        assert f"{decision.score:.1f}" in decision.reason

    def test_decide_returns_complexity_decision(self):
        r = ComplexityRouter()
        decision = r.decide("lista los archivos")
        assert isinstance(decision, ComplexityDecision)
        assert isinstance(decision.signals, tuple)

    def test_empty_task_raises_value_error(self):
        r = ComplexityRouter()
        with pytest.raises(ValueError):
            r.decide("   ")


class TestRoute:
    """API corta route() con selección de modelo."""

    def test_route_returns_correct_model_small(self):
        r = ComplexityRouter()
        out = r.route("lista los archivos", "small-model", "frontier-model")
        assert out["model"] == "small-model"
        assert out["route"] == "small"

    def test_route_returns_correct_model_frontier(self):
        r = ComplexityRouter()
        out = r.route(REASONING_TASK, "small-model", "frontier-model")
        assert out["model"] == "frontier-model"
        assert out["route"] == "frontier"
        assert "score" in out
        assert "reason" in out

    def test_summary_is_readable(self):
        r = ComplexityRouter()
        summary = r.decide(REASONING_TASK).summary()
        assert isinstance(summary, str)
        assert summary
        assert "frontier" in summary
        assert "60.0" in summary


class TestThreshold:
    """Recalibración en caliente del umbral."""

    def test_set_threshold_valid(self):
        r = ComplexityRouter()
        r.set_threshold(50.0)
        assert r.threshold == 50.0
        r.set_threshold(0.0)
        assert r.threshold == 0.0
        r.set_threshold(100.0)
        assert r.threshold == 100.0

    def test_set_threshold_below_zero_raises(self):
        r = ComplexityRouter()
        with pytest.raises(ValueError):
            r.set_threshold(-1)

    def test_set_threshold_above_100_raises(self):
        r = ComplexityRouter()
        with pytest.raises(ValueError):
            r.set_threshold(101)


class TestValidation:
    """Red de seguridad route_with_validation()."""

    def test_validation_false_escalates_to_frontier(self):
        r = ComplexityRouter()
        out = r.route_with_validation(
            "lista los archivos", "small-model", "frontier-model",
            validate_small=lambda task: False,
        )
        assert out["route"] == "frontier"
        assert out["model"] == "frontier-model"

    def test_validation_true_stays_small(self):
        r = ComplexityRouter()
        out = r.route_with_validation(
            "lista los archivos", "small-model", "frontier-model",
            validate_small=lambda task: True,
        )
        assert out["route"] == "small"
        assert out["model"] == "small-model"

    def test_frontier_never_escalates_downward(self):
        """La ruta frontier no escala hacia abajo ni ejecuta el validador."""
        r = ComplexityRouter()
        calls: list[str] = []

        def spy(task: str) -> bool:
            calls.append(task)
            return False

        out = r.route_with_validation(
            REASONING_TASK, "small-model", "frontier-model", validate_small=spy,
        )
        assert out["route"] == "frontier"
        assert out["model"] == "frontier-model"
        assert calls == [], "el validador no debe ejecutarse en ruta frontier"

    def test_validation_exception_escalates_to_frontier(self):
        r = ComplexityRouter()

        def boom(task: str) -> bool:
            raise RuntimeError("validador caído")

        out = r.route_with_validation(
            "lista los archivos", "small-model", "frontier-model", validate_small=boom,
        )
        assert out["route"] == "frontier"
        assert out["model"] == "frontier-model"

    def test_validation_none_skips_validation(self):
        r = ComplexityRouter()
        out = r.route_with_validation(
            "lista los archivos", "small-model", "frontier-model", validate_small=None,
        )
        assert out["route"] == "small"
        assert out["model"] == "small-model"


class TestDomainHint:
    """domain_hint aporta la señal de dominio complejo."""

    def test_domain_hint_adds_complex_domain_signal(self):
        r = ComplexityRouter(domain_hint="legal")
        decision = r.decide(
            "analiza este caso contractual y evalúa los riesgos, justifica la conclusión"
        )
        assert decision.route == "frontier"
        assert "domain_complex" in decision.signals
