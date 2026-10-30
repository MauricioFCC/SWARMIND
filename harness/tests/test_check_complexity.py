"""Tests del gate de complejidad (funciones puras de ``check_complexity``)."""

from __future__ import annotations

import math

import pytest

from scripts import check_complexity as gate


class TestEffectiveRatio:
    """Ratio efectivo por duplicación de escala."""

    def test_linear_growth_is_two(self):
        """Duplicar el coste por cada duplicación de n da ratio 2.0."""
        assert gate._effective_ratio([1.0, 2.0, 4.0]) == pytest.approx(2.0)

    def test_quadratic_growth_is_four(self):
        """Coste cuadrático (n²) da ratio 4.0."""
        assert gate._effective_ratio([1.0, 4.0, 16.0]) == pytest.approx(4.0)

    def test_zero_first_time_is_infinite(self):
        """Un tiempo base nulo no se puede normalizar: ratio infinito."""
        assert math.isinf(gate._effective_ratio([0.0, 1.0, 2.0]))

    def test_single_scale_is_neutral(self, monkeypatch):
        """Con una sola escala no hay duplicaciones: ratio 1.0."""
        monkeypatch.setattr(gate, "SCALES", (100,))
        assert gate._effective_ratio([3.0]) == pytest.approx(1.0)


class TestEvaluate:
    """Umbral absoluto por clase + ratchet contra baseline."""

    def _entry(self, ratio: float, threshold: float = 2.8) -> dict[str, object]:
        return {
            "expected": "linear",
            "times": [0.1, 0.2, 0.4],
            "ratio": ratio,
            "threshold": threshold,
            "ok": ratio <= threshold,
        }

    def test_no_failures_when_below_threshold(self):
        """Un ratio lineal por debajo del umbral pasa."""
        assert gate.evaluate({"bench": self._entry(2.1)}, {}) == []

    def test_fails_when_above_threshold(self):
        """Un hotspot superlineal falla con mensaje accionable."""
        failures = gate.evaluate({"bench": self._entry(3.9)}, {})
        assert len(failures) == 1
        assert "umbral=2.8" in failures[0]

    def test_fails_on_regression_vs_baseline(self):
        """Superar el baseline con margen falla aunque el umbral se cumpla."""
        baseline = {"bench": {"ratio": 1.4}}
        failures = gate.evaluate({"bench": self._entry(2.7)}, baseline)
        assert failures and "regresión vs baseline" in failures[0]

    def test_ratchet_has_noise_floor(self):
        """Con baseline muy bajo, el piso de ruido evita fallos espurios."""
        baseline = {"bench": {"ratio": 1.3}}
        assert gate.evaluate({"bench": self._entry(2.3)}, baseline) == []

    def test_baseline_absent_does_not_fail(self):
        """Sin baseline solo aplica el umbral absoluto."""
        assert gate.evaluate({"bench": self._entry(2.2)}, {}) == []


class TestBaseline:
    """Persistencia del baseline (ratchet portable)."""

    def test_write_and_load_roundtrip(self, tmp_path, monkeypatch):
        """El baseline escrito se puede releer y conserva ratios."""
        target = tmp_path / "complexity_baseline.json"
        monkeypatch.setattr(gate, "BASELINE_PATH", target)
        results = {"bench": {"expected": "linear", "ratio": 2.05, "threshold": 2.6, "ok": True}}
        gate.write_baseline(results)
        loaded = gate.load_baseline()
        assert loaded["bench"]["ratio"] == 2.05
        assert loaded["bench"]["threshold"] == 2.6

    def test_load_missing_baseline_is_empty(self, tmp_path, monkeypatch):
        """Baseline ausente no rompe el gate (solo umbral absoluto)."""
        monkeypatch.setattr(gate, "BASELINE_PATH", tmp_path / "nope.json")
        assert gate.load_baseline() == {}
