"""
Tests for AgentKpiTracker — KPI recording, querying, and dashboard summary.

Covers:
  - Dataclass record creation and to_lancedb_row()
  - AgentKpiTracker initialization with mocked store
  - record_agent_performance()
  - record_skill_effectiveness() (create + update paths)
  - record_telemetry_event()
  - record_session_kpi()
  - record_agent_interaction()
  - get_agent_rankings(), get_skill_rankings(), get_session_history()
  - get_dashboard_summary()
  - Telemetry OFF / BASIC / FULL filtering
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from harness.memory_rag.agent_kpi_tracker import (
    COLL_AGENT_PERFORMANCE,
    COLL_SESSION_KPIS,
    COLL_SKILL_EFFECTIVENESS,
    AgentKpiTracker,
    AgentPerformanceRecord,
    SessionKPIRecord,
    SkillEffectivenessRecord,
    TelemetryEventRecord,
)
from harness.memory_rag.memory_config import MemoryConfig, TelemetryLevel

# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestAgentPerformanceRecord:
    def test_create_defaults(self):
        rec = AgentPerformanceRecord(session_id="s1", agent_name="builder")
        assert rec.session_id == "s1"
        assert rec.agent_name == "builder"
        assert rec.success_count == 0
        assert rec.success_rate == 1.0

    def test_to_lancedb_row_shape(self):
        rec = AgentPerformanceRecord(
            session_id="s1", agent_name="builder", task="deploy",
            subtask_count=5, success_count=4, error_count=1,
            total_duration_ms=12000.0, avg_latency_ms=2400.0,
            tokens_input=1000, tokens_output=500,
            pipeline_type="standard", complexity_score=0.75,
            metadata={"key": "val"},
        )
        row = rec.to_lancedb_row()
        assert row["session_id"] == "s1"
        assert row["agent_name"] == "builder"
        assert row["task"] == "deploy"
        assert row["subtask_count"] == 5
        assert row["success_count"] == 4
        assert row["error_count"] == 1
        assert row["total_duration_ms"] == 12000.0
        assert row["avg_latency_ms"] == 2400.0
        assert row["success_rate"] == 1.0
        assert row["tokens_input"] == 1000
        assert row["tokens_output"] == 500
        assert row["pipeline_type"] == "standard"
        assert row["complexity_score"] == 0.75
        assert json.loads(row["metadata"]) == {"key": "val"}
        assert "id" in row
        assert "created_at" in row

    def test_to_lancedb_rounding(self):
        rec = AgentPerformanceRecord(
            session_id="s1", agent_name="test",
            total_duration_ms=1234.56789,
            avg_latency_ms=99.99999,
            success_rate=0.66666,
            complexity_score=0.12345,
        )
        row = rec.to_lancedb_row()
        assert row["total_duration_ms"] == 1234.57
        assert row["avg_latency_ms"] == 100.0
        assert row["success_rate"] == 0.6667
        assert row["complexity_score"] == 0.123


class TestSkillEffectivenessRecord:
    def test_create_defaults(self):
        rec = SkillEffectivenessRecord(skill_name="test", domain="code")
        assert rec.skill_name == "test"
        assert rec.domain == "code"
        assert rec.use_count == 0

    def test_to_lancedb_row(self):
        rec = SkillEffectivenessRecord(
            skill_name="rust-opt", domain="performance",
            agent="scientist", use_count=10, success_rate=0.95,
            avg_duration_ms=1500.0, avg_tokens_saved=200,
            promotion_count=3, metadata={"lang": "rust"},
        )
        row = rec.to_lancedb_row()
        assert row["skill_name"] == "rust-opt"
        assert row["domain"] == "performance"
        assert row["agent"] == "scientist"
        assert row["use_count"] == 10
        assert row["success_rate"] == 0.95
        assert row["avg_duration_ms"] == 1500.0
        assert row["avg_tokens_saved"] == 200
        assert row["promotion_count"] == 3
        assert json.loads(row["metadata"]) == {"lang": "rust"}
        assert "id" in row
        assert "last_used" in row
        assert "created_at" in row


class TestTelemetryEventRecord:
    def test_create_defaults(self):
        rec = TelemetryEventRecord(event_type="plan_created")
        assert rec.event_type == "plan_created"
        assert rec.level == "info"

    def test_to_lancedb_row(self):
        rec = TelemetryEventRecord(
            event_type="error", session_id="s1", agent="builder",
            level="error", message="connection refused",
            duration_ms=500.0, status="failed",
            tags=["network", "timeout"],
            metadata={"retries": 3},
        )
        row = rec.to_lancedb_row()
        assert row["event_type"] == "error"
        assert row["session_id"] == "s1"
        assert row["agent"] == "builder"
        assert row["level"] == "error"
        assert row["message"] == "connection refused"
        assert row["duration_ms"] == 500.0
        assert row["status"] == "failed"
        assert json.loads(row["tags"]) == ["network", "timeout"]
        assert json.loads(row["metadata"]) == {"retries": 3}
        assert "id" in row
        assert "created_at" in row

    def test_message_truncated_to_500(self):
        long_msg = "x" * 1000
        rec = TelemetryEventRecord(event_type="test", message=long_msg)
        row = rec.to_lancedb_row()
        assert len(row["message"]) == 500


class TestSessionKPIRecord:
    def test_create_defaults(self):
        rec = SessionKPIRecord(session_id="s1")
        assert rec.session_id == "s1"
        assert rec.status == "completed"

    def test_to_lancedb_row(self):
        rec = SessionKPIRecord(
            session_id="s1", task="implement API", project="Swarmind",
            status="completed", total_duration_ms=150000.0,
            total_subtasks=5, total_errors=1, total_warnings=2,
            success_rate=0.8, levels_completed=3, agents_involved=2,
            pipeline_type="standard", complexity="medium",
            metadata={"team": "core"},
        )
        row = rec.to_lancedb_row()
        assert row["session_id"] == "s1"
        assert row["task"] == "implement API"
        assert row["project"] == "Swarmind"
        assert row["status"] == "completed"
        assert row["total_duration_ms"] == 150000.0
        assert row["total_subtasks"] == 5
        assert row["total_errors"] == 1
        assert row["total_warnings"] == 2
        assert row["success_rate"] == 0.8
        assert row["levels_completed"] == 3
        assert row["agents_involved"] == 2
        assert row["pipeline_type"] == "standard"
        assert row["complexity"] == "medium"
        assert json.loads(row["metadata"]) == {"team": "core"}
        assert "id" in row
        assert "created_at" in row
        assert "updated_at" in row

    def test_task_truncated_to_200(self):
        long_task = "x" * 300
        rec = SessionKPIRecord(session_id="s1", task=long_task)
        row = rec.to_lancedb_row()
        assert len(row["task"]) == 200


# ---------------------------------------------------------------------------
# Helpers to build a mocked LanceVectorStore
# ---------------------------------------------------------------------------

def _make_mock_store() -> MagicMock:
    """Create a mocked LanceVectorStore that records inserts and supports search."""
    store = MagicMock()
    store.list_collections.return_value = []
    store.search.return_value = []
    store.insert.return_value = ["mock-uuid"]

    # Track inserts for later inspection (side_effect-free to avoid recursion)
    store.inserted_rows = []

    def tracking_insert(collection, vec, rows, **kwargs):
        store.inserted_rows.extend(rows)
        return ["mock-uuid"]

    store.insert.side_effect = tracking_insert
    return store


def _find_row(rows, **filters):
    """Helper to find a row in inserted data matching filters."""
    for r in rows:
        if all(r.get(k) == v for k, v in filters.items()):
            return r
    return None


# ---------------------------------------------------------------------------
# AgentKpiTracker tests
# ---------------------------------------------------------------------------


class TestAgentKpiTrackerInit:
    def test_init_with_store(self):
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store)
        assert tracker._store is store
        assert tracker._enabled is True

    def test_init_with_custom_config(self):
        config = MemoryConfig(telemetry_level=TelemetryLevel.FULL)
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store, config=config)
        assert tracker._config.telemetry_level == TelemetryLevel.FULL
        assert tracker._full_telemetry is True

    def test_init_telemetry_off(self):
        config = MemoryConfig(telemetry_level=TelemetryLevel.OFF)
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store, config=config)
        assert tracker._enabled is False


class TestRecordAgentPerformance:
    def test_record_returns_id(self):
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store)
        result = tracker.record_agent_performance(
            session_id="s1", agent_name="builder",
            subtask_count=5, success_count=4, error_count=1,
            task="deploy",
        )
        assert result == "mock-uuid"

    def test_record_creates_correct_row(self):
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store)
        tracker.record_agent_performance(
            session_id="s1", agent_name="builder",
            subtask_count=5, success_count=4, error_count=1,
        )
        row = _find_row(store.inserted_rows, session_id="s1")
        assert row is not None
        assert row["agent_name"] == "builder"
        assert row["subtask_count"] == 5
        assert row["success_count"] == 4
        assert row["error_count"] == 1

    def test_record_computes_success_rate(self):
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store)
        tracker.record_agent_performance(
            session_id="s1", agent_name="builder",
            subtask_count=4, success_count=3,
        )
        row = _find_row(store.inserted_rows, session_id="s1")
        assert row["success_rate"] == 0.75

    def test_record_zero_subtasks_defaults_to_1(self):
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store)
        tracker.record_agent_performance(
            session_id="s1", agent_name="builder",
            subtask_count=0, success_count=0,
        )
        row = _find_row(store.inserted_rows, session_id="s1")
        assert row["success_rate"] == 1.0

    def test_telemetry_off_returns_none(self):
        config = MemoryConfig(telemetry_level=TelemetryLevel.OFF)
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store, config=config)
        result = tracker.record_agent_performance(
            session_id="s1", agent_name="builder",
        )
        assert result is None


class TestRecordSkillEffectiveness:
    def test_record_new_skill(self):
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store)
        result = tracker.record_skill_effectiveness(
            skill_name="rust-opt", domain="code",
            agent="scientist", success=True, duration_ms=100.0,
        )
        assert result == "mock-uuid"

    def test_record_new_skill_creates_row(self):
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store)
        tracker.record_skill_effectiveness(
            skill_name="rust-opt", domain="code", agent="scientist",
            success=True, duration_ms=100.0, tokens_saved=50, promoted=True,
        )
        row = _find_row(store.inserted_rows, skill_name="rust-opt")
        assert row is not None
        assert row["domain"] == "code"
        assert row["agent"] == "scientist"
        assert row["success_rate"] == 1.0
        assert row["avg_duration_ms"] == 100.0
        assert row["avg_tokens_saved"] == 50
        assert row["promotion_count"] == 1

    def test_record_skill_failure_rate(self):
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store)
        tracker.record_skill_effectiveness(
            skill_name="buggy", domain="code", agent="builder",
            success=False,
        )
        row = _find_row(store.inserted_rows, skill_name="buggy")
        assert row["success_rate"] == 0.0

    def test_telemetry_off_returns_none(self):
        config = MemoryConfig(telemetry_level=TelemetryLevel.OFF)
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store, config=config)
        result = tracker.record_skill_effectiveness(
            skill_name="test", domain="test", agent="test",
        )
        assert result is None

    def test_update_existing_skill(self):
        """When a skill record already exists, metrics should be updated."""
        store = _make_mock_store()
        # Simulate an existing record
        existing_id = "existing-skill-1"
        existing_row = {
            "id": existing_id,
            "skill_name": "rust-opt",
            "domain": "code",
            "agent": "scientist",
            "use_count": 5,
            "success_rate": 0.8,
            "avg_duration_ms": 200.0,
            "avg_tokens_saved": 100,
            "promotion_count": 1,
            "metadata": json.dumps({"skill_name": "rust-opt", "domain": "code", "agent": "scientist"}),
            "score": 1.0,
        }
        store.search.return_value = [existing_row]

        tracker = AgentKpiTracker(store=store)
        result = tracker.record_skill_effectiveness(
            skill_name="rust-opt", domain="code", agent="scientist",
            success=True, duration_ms=50.0, tokens_saved=30, promoted=True,
        )
        # Should return the existing ID
        assert result == existing_id
        # Should call update_records with correct args
        assert store.update_records.called, "update_records was not called"
        call_args = store.update_records.call_args
        assert call_args is not None
        args, kwargs = call_args
        # First positional arg is collection
        assert args[0] == COLL_SKILL_EFFECTIVENESS
        # filters and updates are keyword args
        assert kwargs["filters"]["id"] == existing_id
        assert kwargs["updates"]["use_count"] == 6
        assert kwargs["updates"]["promotion_count"] == 2


class TestRecordTelemetryEvent:
    def test_record_event_basic(self):
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store)
        # BASIC mode: only important events pass through
        result = tracker.record_telemetry_event(
            event_type="error", session_id="s1",
            level="error", message="timeout",
        )
        assert result == "mock-uuid"

    def test_record_event_basic_filters_minor(self):
        config = MemoryConfig(telemetry_level=TelemetryLevel.BASIC)
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store, config=config)
        # Minor event should be filtered out in BASIC mode
        result = tracker.record_telemetry_event(
            event_type="info", level="info", message="all good",
        )
        assert result is None

    def test_record_event_full_allows_all(self):
        config = MemoryConfig(telemetry_level=TelemetryLevel.FULL)
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store, config=config)
        result = tracker.record_telemetry_event(
            event_type="info", level="info", message="all good",
        )
        assert result == "mock-uuid"

    def test_record_event_important_in_basic(self):
        config = MemoryConfig(telemetry_level=TelemetryLevel.BASIC)
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store, config=config)
        for evt in ("error", "warning", "plan_created", "plan_complete",
                     "circuit_breaker_open", "stall_detected"):
            result = tracker.record_telemetry_event(
                event_type=evt, level="info", message=evt,
            )
            assert result == "mock-uuid", f"{evt} should pass BASIC filter"

    def test_telemetry_off_returns_none(self):
        config = MemoryConfig(telemetry_level=TelemetryLevel.OFF)
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store, config=config)
        result = tracker.record_telemetry_event(
            event_type="error", level="error", message="fail",
        )
        assert result is None


class TestRecordSessionKPI:
    def test_record_new_session_kpi(self):
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store)
        result = tracker.record_session_kpi(
            session_id="s1", task="implement API",
            total_duration_ms=150000.0, total_subtasks=5,
        )
        assert result == "mock-uuid"

    def test_record_session_kpi_creates_row(self):
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store)
        tracker.record_session_kpi(
            session_id="s1", task="implement API",
            total_duration_ms=150000.0, total_subtasks=5,
            status="completed", total_errors=1,
        )
        row = _find_row(store.inserted_rows, session_id="s1")
        assert row is not None
        assert row["total_duration_ms"] == 150000.0
        assert row["total_subtasks"] == 5
        assert row["status"] == "completed"

    def test_telemetry_off_returns_none(self):
        config = MemoryConfig(telemetry_level=TelemetryLevel.OFF)
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store, config=config)
        result = tracker.record_session_kpi(session_id="s1")
        assert result is None

    def test_update_existing_session_kpi(self):
        """When a session KPI already exists, it should be updated."""
        store = _make_mock_store()
        existing_id = "existing-session-1"
        existing_row = {
            "id": existing_id,
            "session_id": "s1",
            "status": "running",
            "total_duration_ms": 50000.0,
            "metadata": json.dumps({"session_id": "s1"}),
            "score": 1.0,
        }
        store.search.return_value = [existing_row]

        tracker = AgentKpiTracker(store=store)
        result = tracker.record_session_kpi(
            session_id="s1", task="implement API",
            total_duration_ms=150000.0, status="completed",
        )
        assert result == existing_id
        store.update_records.assert_called_once()


class TestRecordAgentInteraction:
    def test_record_interaction_full(self):
        config = MemoryConfig(telemetry_level=TelemetryLevel.FULL)
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store, config=config)
        result = tracker.record_agent_interaction(
            session_id="s1", from_agent="builder", to_agent="scientist",
        )
        assert result == "mock-uuid"

    def test_record_interaction_basic_returns_none(self):
        config = MemoryConfig(telemetry_level=TelemetryLevel.BASIC)
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store, config=config)
        result = tracker.record_agent_interaction(
            session_id="s1", from_agent="builder", to_agent="scientist",
        )
        assert result is None

    def test_record_interaction_off_returns_none(self):
        config = MemoryConfig(telemetry_level=TelemetryLevel.OFF)
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store, config=config)
        result = tracker.record_agent_interaction(
            session_id="s1", from_agent="builder", to_agent="scientist",
        )
        assert result is None


# ---------------------------------------------------------------------------
# Query / Reporting tests
# ---------------------------------------------------------------------------


class TestGetAgentRankings:
    def test_returns_empty_when_no_data(self):
        store = _make_mock_store()
        store.search.return_value = []
        tracker = AgentKpiTracker(store=store)
        rankings = tracker.get_agent_rankings()
        assert rankings == []

    def test_aggregates_agent_stats(self):
        store = _make_mock_store()
        store.search.return_value = [
            {"agent_name": "builder", "subtask_count": 10, "success_count": 8,
             "error_count": 2, "total_duration_ms": 50000.0,
             "metadata": json.dumps({"agent_name": "builder"}), "score": 1.0},
            {"agent_name": "builder", "subtask_count": 5, "success_count": 5,
             "error_count": 0, "total_duration_ms": 20000.0,
             "metadata": json.dumps({"agent_name": "builder"}), "score": 1.0},
            {"agent_name": "scientist", "subtask_count": 8, "success_count": 6,
             "error_count": 2, "total_duration_ms": 30000.0,
             "metadata": json.dumps({"agent_name": "scientist"}), "score": 1.0},
        ]
        tracker = AgentKpiTracker(store=store)
        rankings = tracker.get_agent_rankings()
        assert len(rankings) == 2
        # Builder has higher success rate (13/15 ≈ 0.8667 vs 6/8 = 0.75)
        assert rankings[0]["agent_name"] == "builder"
        assert rankings[1]["agent_name"] == "scientist"
        assert rankings[0]["total_sessions"] == 2

    def test_min_sessions_filter(self):
        store = _make_mock_store()
        store.search.return_value = [
            {"agent_name": "builder", "subtask_count": 5, "success_count": 5,
             "error_count": 0, "total_duration_ms": 10000.0,
             "metadata": json.dumps({"agent_name": "builder"}), "score": 1.0},
        ]
        tracker = AgentKpiTracker(store=store)
        rankings = tracker.get_agent_rankings(min_sessions=2)
        assert rankings == []

    def test_search_failure_returns_empty(self):
        store = _make_mock_store()
        store.search.side_effect = Exception("DB error")
        tracker = AgentKpiTracker(store=store)
        rankings = tracker.get_agent_rankings()
        assert rankings == []


class TestGetSkillRankings:
    def test_returns_empty_when_no_data(self):
        store = _make_mock_store()
        store.search.return_value = []
        tracker = AgentKpiTracker(store=store)
        rankings = tracker.get_skill_rankings()
        assert rankings == []

    def test_returns_ranked_skills(self):
        store = _make_mock_store()
        store.search.return_value = [
            {"skill_name": "rust-opt", "domain": "code", "agent": "scientist",
             "use_count": 10, "success_rate": 0.9, "avg_duration_ms": 100.0,
             "promotion_count": 2,
             "metadata": json.dumps({"skill_name": "rust-opt", "domain": "code", "agent": "scientist"}),
             "score": 1.0},
            {"skill_name": "test-gen", "domain": "code", "agent": "builder",
             "use_count": 5, "success_rate": 0.8, "avg_duration_ms": 200.0,
             "promotion_count": 1,
             "metadata": json.dumps({"skill_name": "test-gen", "domain": "code", "agent": "builder"}),
             "score": 1.0},
        ]
        tracker = AgentKpiTracker(store=store)
        rankings = tracker.get_skill_rankings()
        assert len(rankings) == 2
        # Sorted by use_count descending
        assert rankings[0]["skill_name"] == "rust-opt"

    def test_search_failure_returns_empty(self):
        store = _make_mock_store()
        store.search.side_effect = Exception("DB error")
        tracker = AgentKpiTracker(store=store)
        rankings = tracker.get_skill_rankings()
        assert rankings == []


class TestGetSessionHistory:
    def test_returns_empty_when_no_data(self):
        store = _make_mock_store()
        store.search.return_value = []
        tracker = AgentKpiTracker(store=store)
        history = tracker.get_session_history()
        assert history == []

    def test_returns_sessions(self):
        store = _make_mock_store()
        store.search.return_value = [
            {"session_id": "s1", "task": "API", "project": "p1",
             "status": "completed", "total_duration_ms": 100000.0,
             "total_subtasks": 5, "total_errors": 0, "success_rate": 1.0,
             "levels_completed": 3, "agents_involved": 2, "complexity": "medium",
             "metadata": json.dumps({"session_id": "s1"}), "score": 1.0},
            {"session_id": "s2", "task": "test", "project": "p1",
             "status": "failed", "total_duration_ms": 50000.0,
             "total_subtasks": 3, "total_errors": 2, "success_rate": 0.5,
             "levels_completed": 1, "agents_involved": 1, "complexity": "low",
             "metadata": json.dumps({"session_id": "s2"}), "score": 1.0},
        ]
        tracker = AgentKpiTracker(store=store)
        history = tracker.get_session_history()
        assert len(history) == 2

    def test_filters_by_status(self):
        store = _make_mock_store()
        store.search.return_value = [
            {"session_id": "s1", "status": "completed",
             "total_duration_ms": 100000.0, "total_subtasks": 5,
             "total_errors": 0, "success_rate": 1.0,
             "levels_completed": 3, "agents_involved": 2, "complexity": "medium",
             "task": "", "project": "",
             "metadata": json.dumps({"session_id": "s1"}), "score": 1.0},
            {"session_id": "s2", "status": "failed",
             "total_duration_ms": 50000.0, "total_subtasks": 3,
             "total_errors": 2, "success_rate": 0.5,
             "levels_completed": 1, "agents_involved": 1, "complexity": "low",
             "task": "", "project": "",
             "metadata": json.dumps({"session_id": "s2"}), "score": 1.0},
        ]
        tracker = AgentKpiTracker(store=store)
        history = tracker.get_session_history(status="completed")
        assert len(history) == 1
        assert history[0]["session_id"] == "s1"

    def test_search_failure_returns_empty(self):
        store = _make_mock_store()
        store.search.side_effect = Exception("DB error")
        tracker = AgentKpiTracker(store=store)
        history = tracker.get_session_history()
        assert history == []

    def test_sorted_by_duration_desc(self):
        store = _make_mock_store()
        store.search.return_value = [
            {"session_id": "s1", "status": "completed",
             "total_duration_ms": 50000.0, "total_subtasks": 3,
             "total_errors": 0, "success_rate": 1.0,
             "levels_completed": 1, "agents_involved": 1, "complexity": "low",
             "task": "", "project": "",
             "metadata": json.dumps({"session_id": "s1"}), "score": 1.0},
            {"session_id": "s2", "status": "completed",
             "total_duration_ms": 100000.0, "total_subtasks": 5,
             "total_errors": 0, "success_rate": 1.0,
             "levels_completed": 3, "agents_involved": 2, "complexity": "medium",
             "task": "", "project": "",
             "metadata": json.dumps({"session_id": "s2"}), "score": 1.0},
        ]
        tracker = AgentKpiTracker(store=store)
        history = tracker.get_session_history()
        # Longer duration first
        assert history[0]["session_id"] == "s2"


class TestGetDashboardSummary:
    def test_empty_dashboard(self):
        store = _make_mock_store()
        store.search.return_value = []
        tracker = AgentKpiTracker(store=store)
        summary = tracker.get_dashboard_summary()
        assert summary["total_agents_tracked"] == 0
        assert summary["total_skills_tracked"] == 0
        assert summary["recent_sessions"] == []

    def test_dashboard_with_data(self):
        store = _make_mock_store()
        agent_rows = [
            {"agent_name": f"agent-{i}", "subtask_count": 10, "success_count": 9,
             "error_count": 1, "total_duration_ms": 10000.0,
             "metadata": json.dumps({"agent_name": f"agent-{i}"}), "score": 1.0}
            for i in range(3)
        ]
        skill_rows = [
            {"skill_name": f"skill-{i}", "domain": "code", "agent": "test",
             "use_count": 5, "success_rate": 0.9, "avg_duration_ms": 100.0,
             "promotion_count": 0,
             "metadata": json.dumps({"skill_name": f"skill-{i}", "domain": "code", "agent": "test"}),
             "score": 1.0}
            for i in range(3)
        ]
        session_rows = [
            {"session_id": f"s{i}", "task": "task", "project": "p",
             "status": "completed", "total_duration_ms": float(i * 10000),
             "total_subtasks": 5, "total_errors": 0, "success_rate": 1.0,
             "levels_completed": 1, "agents_involved": 1, "complexity": "low",
             "metadata": json.dumps({"session_id": f"s{i}"}), "score": 1.0}
            for i in range(5)
        ]

        def search_side_effect(collection, *args, **kwargs):
            if collection == COLL_AGENT_PERFORMANCE:
                return agent_rows
            elif collection == COLL_SKILL_EFFECTIVENESS:
                return skill_rows
            elif collection == COLL_SESSION_KPIS:
                return session_rows
            return []

        store.search.side_effect = search_side_effect
        tracker = AgentKpiTracker(store=store)
        summary = tracker.get_dashboard_summary()
        assert summary["total_agents_tracked"] == 3
        assert len(summary["top_agents"]) == 3
        assert summary["total_skills_tracked"] == 3
        assert len(summary["top_skills"]) == 3
        assert len(summary["recent_sessions"]) == 5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestFindSkillRecord:
    def test_find_existing_skill(self):
        store = _make_mock_store()
        store.search.return_value = [
            {"skill_name": "rust-opt", "domain": "code", "agent": "scientist",
             "use_count": 5, "metadata": json.dumps({"skill_name": "rust-opt", "domain": "code", "agent": "scientist"}),
             "score": 1.0},
        ]
        tracker = AgentKpiTracker(store=store)
        result = tracker._find_skill_record("rust-opt", "code", "scientist")
        assert result is not None
        assert result["skill_name"] == "rust-opt"

    def test_find_non_existent_skill(self):
        store = _make_mock_store()
        store.search.return_value = []
        tracker = AgentKpiTracker(store=store)
        result = tracker._find_skill_record("nonexistent", "code", "test")
        assert result is None


class TestFindSessionKPI:
    def test_find_existing_session(self):
        store = _make_mock_store()
        store.search.return_value = [
            {"session_id": "s1", "status": "running",
             "metadata": json.dumps({"session_id": "s1"}), "score": 1.0},
        ]
        tracker = AgentKpiTracker(store=store)
        result = tracker._find_session_kpi("s1")
        assert result is not None
        assert result["session_id"] == "s1"

    def test_find_non_existent_session(self):
        store = _make_mock_store()
        store.search.return_value = []
        tracker = AgentKpiTracker(store=store)
        result = tracker._find_session_kpi("nonexistent")
        assert result is None


class TestInsert:
    def test_insert_creates_row(self):
        store = _make_mock_store()
        tracker = AgentKpiTracker(store=store)
        row = {"test": "data"}
        result = tracker._insert("test_collection", row)
        assert result == "mock-uuid"
        store.insert.assert_called_once()

    def test_insert_failure_returns_none(self):
        store = _make_mock_store()
        store.insert.side_effect = Exception("insert failed")
        tracker = AgentKpiTracker(store=store)
        result = tracker._insert("test_collection", {"test": "data"})
        assert result is None
