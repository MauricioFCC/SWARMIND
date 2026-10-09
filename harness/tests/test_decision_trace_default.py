"""Tests para el trace global (singleton) de decision_trace.

Verifican que `default_trace` devuelve siempre la misma instancia, que
`reset_default_trace` la reinicia, y que registra/recupera por task_id.
"""

from __future__ import annotations

from harness.orchestrator.decision_trace import (
    DecisionRecord,
    default_trace,
    reset_default_trace,
)


def test_default_trace_is_singleton() -> None:
    """Dos llamadas devuelven la misma instancia compartida."""
    reset_default_trace()
    assert default_trace() is default_trace()


def test_default_trace_records_and_filters_by_task_id() -> None:
    """El singleton registra y recupera por task_id."""
    reset_default_trace()
    trace = default_trace()
    trace.record(DecisionRecord(strategy="keyword", agent="builder", task_id="t1"))
    trace.record(DecisionRecord(strategy="keyword", agent="guardian", task_id="t2"))
    assert [r["agent"] for r in trace.get_trace("t1")] == ["builder"]
    assert trace.last_decision().agent == "guardian"


def test_reset_default_trace_clears_singleton() -> None:
    """reset deja el singleton limpio (nueva instancia)."""
    first = default_trace()
    reset_default_trace()
    assert default_trace() is not first
