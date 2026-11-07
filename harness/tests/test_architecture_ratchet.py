"""Tests del ratchet de deuda arquitectonica (F7)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "check_architecture.py"


def _load_script() -> ModuleType:
    """Carga ``scripts/check_architecture.py`` como modulo aislado."""
    spec = importlib.util.spec_from_file_location("check_architecture_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script(tmp_path, monkeypatch):
    """Modulo del checker con baseline temporal."""
    module = _load_script()
    monkeypatch.setattr(module, "RATCHET_BASELINE", tmp_path / "baseline.json")
    return module


def test_ratchet_passes_without_increase(script, tmp_path):
    """F7 pasa si los conteos no superan el baseline."""
    (tmp_path / "baseline.json").write_text(
        json.dumps({"rules": {"F3": 2, "F5": 3}}), encoding="utf-8"
    )
    findings = {"F3": ["a", "b"], "F5": ["x", "y", "z"]}
    assert script.check_debt_ratchet(findings) == []


def test_ratchet_blocks_increase(script, tmp_path):
    """F7 bloquea cuando la deuda crece respecto al baseline."""
    (tmp_path / "baseline.json").write_text(
        json.dumps({"rules": {"F3": 1, "F5": 3}}), encoding="utf-8"
    )
    findings = {"F3": ["a", "b"], "F5": ["x", "y", "z"]}
    errors = script.check_debt_ratchet(findings)
    assert len(errors) == 1
    assert "F3" in errors[0]
    assert "1 -> 2" in errors[0]


def test_ratchet_allows_decrease(script, tmp_path):
    """Reducir deuda siempre pasa (el ratchet no exige igualar el baseline)."""
    (tmp_path / "baseline.json").write_text(
        json.dumps({"rules": {"F3": 5, "F5": 5}}), encoding="utf-8"
    )
    assert script.check_debt_ratchet({"F3": [], "F5": ["x"]}) == []


def test_ratchet_missing_baseline_is_error(script, tmp_path):
    """Sin baseline, F7 falla con mensaje accionable."""
    errors = script.check_debt_ratchet({"F3": [], "F5": []})
    assert errors and "falta el baseline" in errors[0]


def test_write_baseline_records_current_counts(script, tmp_path):
    """write_debt_baseline congela los conteos actuales."""
    path = script.write_debt_baseline({"F3": ["a"], "F5": ["b", "c"]})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["rules"] == {"F3": 1, "F5": 2}
    assert path == tmp_path / "baseline.json"


def test_gate_includes_ratchet_only_with_flag(script, monkeypatch):
    """--gate sin --ratchet no evalua F7; con --ratchet si."""
    calls: list[bool] = []

    def _fake_run_checks(ratchet: bool = False):
        calls.append(ratchet)
        findings = {"F1": [], "F2": [], "F3": [], "F4": [], "F5": [], "F6": []}
        if ratchet:
            findings["F7"] = []
        return findings

    monkeypatch.setattr(script, "run_checks", _fake_run_checks)
    assert script.main(["--gate"]) == 0
    assert script.main(["--gate", "--ratchet"]) == 0
    assert calls == [False, True]
