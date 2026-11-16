"""Tests para LatencyWindow (percentiles y ventana acotada)."""

from __future__ import annotations

import pytest

from harness.observability.latency import LatencyWindow


def test_empty_window_returns_zeros() -> None:
    """Sin muestras el resumen es cero, no un error."""
    assert LatencyWindow().stats() == {
        "count": 0,
        "mean": 0.0,
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "max": 0.0,
    }


def test_percentiles_use_nearest_rank() -> None:
    """p50/p95/p99 siguen el mismo criterio que GoldenSignals."""
    window = LatencyWindow(capacity=10)
    for value in range(1, 11):
        window.observe(float(value))

    stats = window.stats()
    assert stats["count"] == 10
    assert stats["p50"] == pytest.approx(5.0)
    assert stats["p95"] == pytest.approx(10.0)
    assert stats["p99"] == pytest.approx(10.0)
    assert stats["max"] == pytest.approx(10.0)
    assert stats["mean"] == pytest.approx(5.5)


def test_window_is_bounded_and_keeps_latest() -> None:
    """Al llenarse se descartan las muestras mas antiguas."""
    window = LatencyWindow(capacity=3)
    for value in (1.0, 2.0, 3.0, 4.0):
        window.observe(value)

    stats = window.stats()
    assert stats["count"] == 3
    assert stats["max"] == pytest.approx(4.0)
    assert stats["p50"] == pytest.approx(3.0)


def test_ignores_non_finite_and_negative_samples() -> None:
    """Muestras invalidas no contaminan los percentiles."""
    window = LatencyWindow()
    window.observe(float("nan"))
    window.observe(float("inf"))
    window.observe(-1.0)

    assert window.count() == 0


def test_capacity_must_be_positive() -> None:
    """Una ventana sin capacidad es un error de configuracion."""
    with pytest.raises(ValueError):
        LatencyWindow(capacity=0)
