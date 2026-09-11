"""Tests para pressure meter + prune_then_summarize (ADR-0077).

deepseek-harness: token-meter determinista (pressure/projected sin LLM) y
compactacion en 2 fases (prune tool-results primero, summarize despues).
"""

import pytest

from harness.memory_rag.compaction_pipeline import prune_then_summarize
from harness.memory_rag.token_usage_tracker import TokenUsageTracker, UsageRecord


def _rec(agent: str = "builder", model: str = "m", inp: int = 100, out: int = 50) -> UsageRecord:
    """Fabrica un UsageRecord simple."""
    return UsageRecord(agent, model, inp, out)


def test_pressure_ratio() -> None:
    """pressure = used/budget con budget dado (determinista, sin LLM)."""
    tracker = TokenUsageTracker()
    for _ in range(4):
        tracker.record(_rec(inp=2000, out=500))
    assert tracker.pressure(budget_tokens=20000) == pytest.approx(10000 / 20000)


def test_pressure_zero_budget_raises() -> None:
    """Budget <= 0 falla accionable."""
    tracker = TokenUsageTracker()
    with pytest.raises(ValueError, match="WHAT"):
        tracker.pressure(budget_tokens=0)


def test_pressure_empty_zero() -> None:
    """Sin registros, presion 0.0."""
    assert TokenUsageTracker().pressure(budget_tokens=1000) == 0.0


def test_prune_then_summarize_pipeline() -> None:
    """Fase 1 evicta tool outputs grandes; fase 2 compacta lo restante."""
    tool_line = "tool result: " + "z" * 500
    session = "\n".join(f"2026 INFO [t{i}] {tool_line}" for i in range(60))
    out = prune_then_summarize(session)
    assert "artifact" in out.lower() or "handle" in out.lower()
    assert len(out) < len(session)


def test_prune_then_summarize_small_passthrough() -> None:
    """Sesion pequena sin tool outputs pasa casi integra."""
    small = "turno 1: hola\nturno 2: adios"
    out = prune_then_summarize(small)
    assert "hola" in out
