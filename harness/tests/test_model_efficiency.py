"""Tests para telemetria de eficiencia por modelo (ADR-0074).

Frontera (Copilot harness 2026): el mismo harness varia hasta 40% en
tokens entre modelos; medir tokens/llamada y costo por modelo permite
re-ponderar el routing. Verifica: agrupacion por modelo, tokens/llamada
y reporte legible.
"""

import pytest

from harness.memory_rag.token_usage_tracker import (
    TokenUsageTracker,
    UsageRecord,
)


def _rec(model: str, agent: str = "builder", inp: int = 100, out: int = 50) -> UsageRecord:
    """Fabrica un UsageRecord simple."""
    return UsageRecord(agent, model, inp, out)


def test_tokens_per_call_by_model() -> None:
    """Tokens por llamada agrupados por modelo."""
    tracker = TokenUsageTracker()
    for _ in range(4):
        tracker.record(_rec("small", inp=200, out=100))
    tracker.record(_rec("frontier", inp=2000, out=800))
    report = tracker.model_efficiency_report()
    small = next(m for m in report if m.model == "small")
    frontier = next(m for m in report if m.model == "frontier")
    assert small.calls == 4
    assert small.avg_total_tokens == pytest.approx(300.0)
    assert frontier.calls == 1
    assert frontier.avg_total_tokens == pytest.approx(2800.0)


def test_report_sorted_by_avg_desc() -> None:
    """El reporte se ordena por avg_total_tokens descendente."""
    tracker = TokenUsageTracker()
    tracker.record(_rec("a", inp=10, out=10))
    tracker.record(_rec("b", inp=900, out=100))
    report = tracker.model_efficiency_report()
    assert report[0].model == "b"


def test_empty_tracker_empty_report() -> None:
    """Sin registros, reporte vacio (tupla)."""
    assert TokenUsageTracker().model_efficiency_report() == ()


def test_report_entry_is_frozen() -> None:
    """Las entradas del reporte son inmutables."""
    tracker = TokenUsageTracker()
    tracker.record(_rec("a"))
    (entry,) = tracker.model_efficiency_report()
    with pytest.raises(AttributeError):
        entry.avg_total_tokens = 1.0  # type: ignore[misc]
