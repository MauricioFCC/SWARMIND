"""Tests del ratchet de Ruff (conteo por regla + baseline)."""

from __future__ import annotations

from scripts import check_ruff_ratchet as ratchet


class TestCountByRule:
    """Agregación de hallazgos por código."""

    def test_groups_and_sorts(self):
        """Cuenta por código y ordena alfabéticamente."""
        findings = [
            {"code": "PERF401"},
            {"code": "FURB103"},
            {"code": "PERF401"},
        ]
        assert ratchet.count_by_rule(findings) == {"FURB103": 1, "PERF401": 2}

    def test_missing_code_is_bucketed(self):
        """Un hallazgo sin código no rompe el conteo."""
        assert ratchet.count_by_rule([{}]) == {"SIN_CODIGO": 1}

    def test_empty_findings(self):
        """Sin hallazgos el mapa es vacío."""
        assert ratchet.count_by_rule([]) == {}


class TestEvaluate:
    """Solo los incrementos son regresiones (ratchet)."""

    def test_no_change_passes(self):
        """Mismo conteo no falla."""
        assert ratchet.evaluate({"PERF401": 5}, {"PERF401": 5}) == []

    def test_decrease_passes(self):
        """Bajar el conteo es el objetivo del ratchet."""
        assert ratchet.evaluate({"PERF401": 3}, {"PERF401": 5}) == []

    def test_increase_fails_with_delta(self):
        """Subir el conteo falla e informa el delta."""
        failures = ratchet.evaluate({"PERF401": 7}, {"PERF401": 5})
        assert failures == ["PERF401: 5 -> 7 (+2)"]

    def test_new_rule_with_findings_fails(self):
        """Una regla nueva con hallazgos cuenta como incremento desde 0."""
        assert ratchet.evaluate({"FURB999": 1}, {}) == ["FURB999: 0 -> 1 (+1)"]

    def test_rule_disappears_passes(self):
        """Una regla que desaparece del reporte no es regresión."""
        assert ratchet.evaluate({}, {"PERF401": 5}) == []


class TestBaseline:
    """Persistencia del baseline."""

    def test_roundtrip(self, tmp_path, monkeypatch):
        """El baseline escrito se relee con los mismos conteos."""
        target = tmp_path / "ruff_baseline.json"
        monkeypatch.setattr(ratchet, "BASELINE_PATH", target)
        ratchet.write_baseline({"PERF401": 2})
        assert ratchet.load_baseline() == {"PERF401": 2}

    def test_missing_baseline_is_empty(self, tmp_path, monkeypatch):
        """Baseline ausente equivale a cero (todo incremento falla)."""
        monkeypatch.setattr(ratchet, "BASELINE_PATH", tmp_path / "nope.json")
        assert ratchet.load_baseline() == {}
