"""Tests para CascadeRouter — patron STEER-lite (intenta small, escala si hay duda).

Complementa a ComplexityRouter (decide una vez) con ejecucion en cascada:
small primero y escalado a frontier cuando la confianza < umbral, con
escape_hatch forzado y contabilidad de costo por intento para calibrar
thresholds offline (frontera 2026: routing+caching+batch hasta -67%).

Los fakes inyectan decide_fn/execute_fn puros: sin LLM, sin red.
"""

import pytest

from harness.model_router.cascade_router import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    CascadeRouter,
)


def _decide(route: str, confidence: float):
    """Fabrica decide_fn que siempre retorna (route, confidence)."""

    def _fn(task: str) -> tuple[str, float]:
        return route, confidence

    return _fn


def _execute(confidences: list[float], tokens: tuple[int, int] = (100, 20)):
    """Fabrica execute_fn con confianzas programadas por intento."""
    calls: list[str] = []

    def _fn(tier: str, task: str) -> tuple[float, int, int]:
        calls.append(tier)
        conf = confidences[min(len(calls) - 1, len(confidences) - 1)]
        return conf, tokens[0], tokens[1]

    _fn.calls = calls  # type: ignore[attr-defined]
    return _fn


def test_small_confident_single_attempt() -> None:
    """Small con confianza alta ejecuta una sola vez en small."""
    router = CascadeRouter(decide_fn=_decide("small", 0.9))
    result = router.run("resume esto", _execute([0.95]))
    assert result.final_route == "small"
    assert len(result.attempts) == 1
    assert result.attempts[0].escalated is False
    assert result.total_cost_usd > 0.0


def test_small_doubtful_escalates_to_frontier() -> None:
    """Small con confianza bajo umbral escala a frontier (2 intentos)."""
    router = CascadeRouter(decide_fn=_decide("small", 0.4))
    result = router.run("resume esto", _execute([0.3, 0.95]))
    assert result.final_route == "frontier"
    assert [a.route for a in result.attempts] == ["small", "frontier"]
    assert result.attempts[1].escalated is True


def test_frontier_route_direct() -> None:
    """Ruta frontier ejecuta directo sin pasar por small."""
    router = CascadeRouter(decide_fn=_decide("frontier", 0.9))
    result = router.run("disena la arquitectura", _execute([0.9]))
    assert result.final_route == "frontier"
    assert len(result.attempts) == 1


def test_escape_hatch_forces_tier() -> None:
    """escape_hatch fuerza el tier pedido ignorando la decision."""
    router = CascadeRouter(decide_fn=_decide("small", 0.99))
    result = router.run("x", _execute([0.9]), force_tier="frontier")
    assert result.final_route == "frontier"
    assert len(result.attempts) == 1


def test_cost_uses_price_table() -> None:
    """El costo total usa la tabla de precios por tier y tokens."""
    router = CascadeRouter(decide_fn=_decide("small", 0.9))
    result = router.run("x", _execute([0.9], tokens=(1000, 500)))
    small = router.price_table["small"]
    expected = (1000 * small.input_per_mtok + 500 * small.output_per_mtok) / 1_000_000
    assert result.total_cost_usd == pytest.approx(expected)


def test_attempts_log_enables_calibration() -> None:
    """Cada intento registra (route, confidence, cost) para calibrar offline."""
    router = CascadeRouter(decide_fn=_decide("small", 0.4))
    result = router.run("x", _execute([0.2, 0.9]))
    for attempt in result.attempts:
        assert attempt.route in ("small", "frontier")
        assert 0.0 <= attempt.confidence <= 1.0
        assert attempt.cost_usd >= 0.0


def test_empty_task_raises() -> None:
    """Task vacia falla con ValueError accionable."""
    router = CascadeRouter(decide_fn=_decide("small", 0.9))
    with pytest.raises(ValueError, match="WHAT"):
        router.run("   ", _execute([0.9]))


def test_invalid_tier_raises() -> None:
    """ Tier desconocido del decide_fn falla con ValueError accionable."""
    router = CascadeRouter(decide_fn=_decide("xlarge", 0.9))
    with pytest.raises(ValueError, match="WHAT"):
        router.run("x", _execute([0.9]))


def test_default_threshold_constant() -> None:
    """El umbral por defecto es 0.7 (documentado y calibrable)."""
    assert DEFAULT_CONFIDENCE_THRESHOLD == 0.7


def test_boundary_confidence_no_escalate() -> None:
    """Confianza exactamente == umbral NO escala (gate estricto <)."""
    router = CascadeRouter(decide_fn=_decide("small", 0.7))
    result = router.run("x", _execute([0.7]))
    assert result.final_route == "small"
    assert len(result.attempts) == 1
