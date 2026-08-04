"""Tests para Decision Trace (X-Swarmind-Decision) — ADR-0033, OmniRoute."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from harness.orchestrator.decision_trace import (
    DecisionRecord,
    DecisionTrace,
    format_decision_header,
)

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def sample_record() -> DecisionRecord:
    """DecisionRecord de ejemplo con valores deterministas."""
    return DecisionRecord(
        strategy="round_robin",
        agent="agent-alpha",
        provider="anthropic",
        latency_ms=123.5,
        score=0.875,
        timestamp=1000.0,
        task_id="task-42",
    )


def _strategies_of(trace: DecisionTrace) -> set[str]:
    """Extrae los strategies presentes en un trace via to_json."""
    return {rec["strategy"] for rec in json.loads(trace.to_json())}


# ===========================================================================
# Test: DecisionRecord
# ===========================================================================


class TestDecisionRecord:
    """Validacion del registro de decision individual."""

    def test_defaults(self) -> None:
        """Los campos con default deben inicializarse correctamente."""
        record = DecisionRecord(strategy="s", agent="a", timestamp=1.0)
        assert record.provider == ""
        assert record.latency_ms == 0.0
        assert record.score == 0.0
        assert record.task_id == ""

    def test_to_dict_serializable(self, sample_record: DecisionRecord) -> None:
        """to_dict debe devolver un dict JSON-serializable."""
        data = sample_record.to_dict()
        assert data["strategy"] == "round_robin"
        assert data["agent"] == "agent-alpha"
        assert data["provider"] == "anthropic"
        assert data["latency_ms"] == 123.5
        assert data["score"] == 0.875
        assert data["timestamp"] == 1000.0
        assert data["task_id"] == "task-42"
        json.dumps(data)  # no debe lanzar

    def test_to_header_exact_format(self) -> None:
        """to_header debe respetar el formato exacto del header."""
        record = DecisionRecord(
            strategy="s",
            agent="a",
            provider="p",
            latency_ms=1.5,
            score=0.9,
            timestamp=2.0,
            task_id="t",
        )
        assert record.to_header() == (
            "X-Swarmind-Decision: strategy=s; agent=a; provider=p; "
            "latency_ms=1.5; score=0.9"
        )

    def test_format_decision_header_alias(self, sample_record: DecisionRecord) -> None:
        """format_decision_header debe ser alias de to_header."""
        assert format_decision_header(sample_record) == sample_record.to_header()


# ===========================================================================
# Test: DecisionTrace
# ===========================================================================


class TestDecisionTrace:
    """Validacion del trace de decisiones por task_id."""

    def test_record_returns_string_id(self) -> None:
        """record debe devolver un id string no vacio y unico."""
        trace = DecisionTrace()
        id_a = trace.record(
            DecisionRecord(strategy="s", agent="a", task_id="t1", timestamp=1.0)
        )
        id_b = trace.record(
            DecisionRecord(strategy="s", agent="b", task_id="t2", timestamp=2.0)
        )
        assert isinstance(id_a, str)
        assert id_a
        assert id_a != id_b

    def test_get_trace_filters_by_task_id(self) -> None:
        """get_trace debe filtrar registros por task_id."""
        trace = DecisionTrace()
        trace.record(
            DecisionRecord(strategy="s1", agent="a1", task_id="task-1", timestamp=1.0)
        )
        trace.record(
            DecisionRecord(strategy="s2", agent="a2", task_id="task-2", timestamp=2.0)
        )
        trace.record(
            DecisionRecord(strategy="s3", agent="a3", task_id="task-1", timestamp=3.0)
        )
        result = trace.get_trace("task-1")
        assert len(result) == 2
        assert {rec["strategy"] for rec in result} == {"s1", "s3"}
        assert all(rec["task_id"] == "task-1" for rec in result)

    def test_get_trace_empty_for_unknown_task(self) -> None:
        """get_trace de un task_id inexistente debe devolver lista vacia."""
        assert DecisionTrace().get_trace("no-existe") == []

    def test_lru_eviction_removes_oldest_timestamp(self) -> None:
        """Con max_records=2, el registro con timestamp mas viejo se evicta."""
        trace = DecisionTrace(max_records=2)
        trace.record(
            DecisionRecord(strategy="old", agent="a", task_id="t1", timestamp=10.0)
        )
        trace.record(
            DecisionRecord(strategy="mid", agent="b", task_id="t2", timestamp=20.0)
        )
        trace.record(
            DecisionRecord(strategy="new", agent="c", task_id="t3", timestamp=30.0)
        )
        data = json.loads(trace.to_json())
        assert len(data) == 2
        assert {rec["strategy"] for rec in data} == {"mid", "new"}

    def test_eviction_prefers_timestamp_over_insertion_order(self) -> None:
        """La eviction elimina por timestamp, no por orden de insercion."""
        trace = DecisionTrace(max_records=2)
        trace.record(
            DecisionRecord(strategy="a", agent="a1", task_id="t1", timestamp=50.0)
        )
        trace.record(
            DecisionRecord(strategy="b", agent="b1", task_id="t2", timestamp=5.0)
        )
        trace.record(
            DecisionRecord(strategy="c", agent="c1", task_id="t3", timestamp=40.0)
        )
        assert _strategies_of(trace) == {"a", "c"}

    def test_last_decision_returns_most_recent_record(self) -> None:
        """last_decision debe devolver el ultimo registro insertado."""
        trace = DecisionTrace()
        trace.record(DecisionRecord(strategy="s1", agent="a1", timestamp=1.0))
        trace.record(DecisionRecord(strategy="s2", agent="a2", timestamp=2.0))
        last = trace.last_decision()
        assert last is not None
        assert last.strategy == "s2"

    def test_last_decision_none_on_empty(self) -> None:
        """last_decision de un trace vacio debe ser None."""
        assert DecisionTrace().last_decision() is None

    def test_clear_empties_trace(self) -> None:
        """clear debe vaciar el trace por completo."""
        trace = DecisionTrace()
        trace.record(
            DecisionRecord(strategy="s", agent="a", task_id="t", timestamp=1.0)
        )
        trace.clear()
        assert trace.last_decision() is None
        assert json.loads(trace.to_json()) == []

    def test_to_json_valid_json(self, sample_record: DecisionRecord) -> None:
        """to_json debe serializar el trace completo como JSON valido."""
        trace = DecisionTrace()
        trace.record(sample_record)
        assert json.loads(trace.to_json()) == [sample_record.to_dict()]

    def test_thread_safety_concurrent_records(self) -> None:
        """Inserciones concurrentes no deben perder registros."""
        trace = DecisionTrace(max_records=1000)

        def record_at(i: int) -> str:
            return trace.record(
                DecisionRecord(
                    strategy=f"s{i}",
                    agent=f"a{i}",
                    task_id="t",
                    timestamp=float(i),
                )
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(record_at, range(100)))
        assert len(json.loads(trace.to_json())) == 100

    def test_invalid_max_records_raises(self) -> None:
        """max_records menor a 1 debe lanzar ValueError."""
        with pytest.raises(ValueError):
            DecisionTrace(max_records=0)
