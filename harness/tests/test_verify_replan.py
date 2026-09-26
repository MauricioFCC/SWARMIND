"""Tests para verify_replan_gate + trace_viewer (ADR-0079).

Frontera: VMAO (ICLR26, Plan-Execute-Verify-Replan; stop si >=80% completo
o 75% confianza+50% completo; tokens Exec 61%/Verify 16%/Synthesis 10%) y
OMA Run Viewer (trace store inspeccionable + replay determinista sin
modelo). Verifica: gate con umbrales VMAO, export trace.jsonl y replay
que re-ejecuta decisiones registradas sin LLM.
"""

import json

import pytest

from harness.orchestrator.trace_viewer import (
    export_trace,
    replay_trace,
)
from harness.orchestrator.verify_replan_gate import (
    STOP_COMPLETE,
    STOP_CONF_COMPLETE,
    GateDecision,
    VerifyReplanGate,
)


def test_gate_continues_when_incomplete() -> None:
    """Plan 40% completo, confianza 0.5 -> CONTINUE (replan)."""
    gate = VerifyReplanGate()
    out = gate.evaluate(completion=0.4, confidence=0.5)
    assert out.decision is GateDecision.REPLAN
    assert out.stop is False


def test_gate_stops_at_80_complete() -> None:
    """Plan >= 80% completo -> STOP (suficiente)."""
    gate = VerifyReplanGate()
    out = gate.evaluate(completion=0.8, confidence=0.4)
    assert out.decision is GateDecision.STOP
    assert out.stop is True


def test_gate_stops_conf_complete_combo() -> None:
    """Confianza >= 75% + completo >= 50% -> STOP."""
    gate = VerifyReplanGate()
    out = gate.evaluate(completion=0.5, confidence=0.75)
    assert out.stop is True


def test_gate_invalid_inputs_raise() -> None:
    """completion/confidence fuera de [0,1] fallan accionable."""
    gate = VerifyReplanGate()
    with pytest.raises(ValueError, match="WHAT"):
        gate.evaluate(completion=1.2, confidence=0.5)
    with pytest.raises(ValueError, match="WHAT"):
        gate.evaluate(completion=0.5, confidence=-0.1)


def test_constants_vmao() -> None:
    """Constantes VMAO: 0.80 completo, 0.75 conf + 0.50 completo."""
    assert STOP_COMPLETE == 0.8
    assert STOP_CONF_COMPLETE == (0.75, 0.5)


def test_export_trace_jsonl(tmp_path) -> None:
    """Exporta decisiones a trace.jsonl (1 linea por decision)."""
    decisions = [
        {"agent": "builder", "action": "edit", "task_id": "t1"},
        {"agent": "guardian", "action": "verify", "task_id": "t1"},
    ]
    path = export_trace(decisions, tmp_path / "trace.jsonl")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["agent"] == "builder"


def test_replay_trace_deterministic(tmp_path) -> None:
    """Replay re-ejecuta decisiones sin LLM (mismo orden, conteo)."""
    decisions = [
        {"agent": "a", "action": "x", "task_id": "t"},
        {"agent": "b", "action": "y", "task_id": "t"},
    ]
    path = export_trace(decisions, tmp_path / "trace.jsonl")
    calls: list[str] = []

    def player(decision: dict) -> str:
        calls.append(decision["action"])
        return "ok"

    results = replay_trace(path, player)
    assert calls == ["x", "y"]
    assert results == ["ok", "ok"]


def test_replay_missing_file_raises(tmp_path) -> None:
    """Archivo inexistente falla accionable."""
    with pytest.raises(FileNotFoundError, match="WHAT"):
        replay_trace(tmp_path / "no-existe.jsonl", lambda d: "x")
