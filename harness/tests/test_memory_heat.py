"""Tests de politica de calor y eviccion (STM/MTM/LTM, MemoryOS)."""

from __future__ import annotations

import datetime as dt

import pytest

from harness.memory_rag.memory_heat import (
    HeatPolicy,
    apply_heat_policy,
    heat_score,
    plan_eviction,
    segment_for,
)
from harness.memory_rag.ruscadb_store import RuscaDBStore

try:
    from harness.memory_rag.ruscadb import load_library

    load_library()
    _RUSCADB_AVAILABLE = True
except Exception:  # noqa: BLE001
    _RUSCADB_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _RUSCADB_AVAILABLE, reason="RuscaDB C-ABI dll not available"
)

NOW = dt.datetime(2026, 10, 30, tzinfo=dt.UTC)


@pytest.fixture
def store(tmp_path):
    """Store aislado con coleccion ``mem``."""
    s = RuscaDBStore(db_path=str(tmp_path / "heat.db"))
    s.create_collection("mem")
    yield s
    s.close()


def test_heat_score_decays_with_age():
    """El score baja con la edad y sube con el uso."""
    fresh = heat_score(4, NOW.isoformat(), NOW, 30.0)
    old_stamp = (NOW - dt.timedelta(days=60)).isoformat()
    old = heat_score(4, old_stamp, NOW, 30.0)
    assert fresh == pytest.approx(4.0)
    assert old == pytest.approx(1.0, rel=1e-6)
    assert heat_score(0, NOW.isoformat(), NOW, 30.0) == 0.0
    assert heat_score(3, "no-es-fecha", NOW, 30.0) == 0.0


def test_segment_for_boundaries():
    """STM/MTM/LTM se separan por antiguedad."""
    policy = HeatPolicy(stm_max_age_hours=24, mtm_max_age_days=7)
    assert segment_for(0.5, policy) == "stm"
    assert segment_for(3.0, policy) == "mtm"
    assert segment_for(30.0, policy) == "ltm"


def test_half_life_per_collection():
    """El override por coleccion tiene prioridad sobre el global."""
    policy = HeatPolicy(half_life_days=30.0, per_collection_half_life={"mem": 7.0})
    assert policy.half_life_for("mem") == 7.0
    assert policy.half_life_for("otra") == 30.0


def test_plan_eviction_only_cold_and_old():
    """Solo se evacuan entradas antiguas con heat bajo."""
    old = (NOW - dt.timedelta(days=365)).isoformat()
    entries = [
        {"id": "fria", "created_at": old, "metadata": {"access_count": 0}},
        {"id": "caliente", "created_at": old,
         "metadata": {"access_count": 10,
                      "last_accessed": (NOW - dt.timedelta(days=1)).isoformat()}},
        {"id": "nueva", "created_at": NOW.isoformat(), "metadata": {}},
    ]
    targets = plan_eviction(entries, HeatPolicy(), NOW, collection="mem")
    assert "nueva" not in targets
    assert "caliente" not in targets


def test_apply_heat_policy_marks_evicted_and_retrieval_hides(store):
    """La eviccion es reversible: marca ``evicted`` y el retrieval la oculta."""
    old = "2020-01-01T00:00:00+00:00"
    store.insert(
        "mem",
        [[1.0, 0.0]],
        [{"trust_tier": "user_stated"}],
        texts=["memoria vieja"],
        now=old,
    )
    report = apply_heat_policy(
        store, "mem", HeatPolicy(evict_after_days=1, min_heat=5.0), NOW
    )
    assert report.scanned == 1
    assert report.evicted == 1
    assert report.segments["ltm"] == 1
    assert store.search("mem", [1.0, 0.0], top_k=5) == []
    visible = store.search("mem", [1.0, 0.0], top_k=5, include_evicted=True)
    assert visible and visible[0]["metadata"]["evicted"] is True


def test_heat_policy_drives_recency_by_default(store, tmp_path):
    """Con heat_policy inyectada, search aplica su vida media sin pasar kwargs."""
    old = "2021-01-01T00:00:00+00:00"
    store.insert("mem", [[1.0, 0.0]], [{"trust_tier": "user_stated"}],
                 texts=["vieja"], now=old)
    store.insert("mem", [[0.0, 1.0]], [{"trust_tier": "user_stated"}],
                 texts=["nueva"])
    policy = HeatPolicy(half_life_days=30.0)
    store._heat_policy = policy
    results = store.search("mem", [1.0, 0.0], top_k=5)
    assert results[0]["text"] == "nueva"
    assert results[0]["recency_weight"] > results[-1]["recency_weight"]
