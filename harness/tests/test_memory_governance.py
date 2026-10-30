"""Tests del write gate (MemoryGuard) y del refuerzo por uso (record_access)."""

from __future__ import annotations

import pytest

from harness.memory_rag.memory_guard import MemoryGuard
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


SCHEMA = {"text": str, "trust_tier": str}


@pytest.fixture
def guarded_store(tmp_path):
    """Store con MemoryGuard inyectado (schema minimo explicito)."""
    guard = MemoryGuard({"mem": SCHEMA})
    store = RuscaDBStore(db_path=str(tmp_path / "guard.db"), memory_guard=guard)
    store.create_collection("mem")
    yield store
    store.close()


@pytest.fixture
def store(tmp_path):
    """Store sin guard (comportamiento por defecto)."""
    s = RuscaDBStore(db_path=str(tmp_path / "plain.db"))
    s.create_collection("mem")
    yield s
    s.close()


def test_write_gate_quarantines_invalid_record(guarded_store):
    """Un record que no cumple el schema se marca en cuarentena, no se pierde."""
    ids = guarded_store.insert(
        "mem", [[1.0, 0.0]], [{"text": "ok", "trust_tier": "user_stated", "extra": 1}]
    )
    assert len(ids) == 1
    raw = guarded_store.execute("SELECT * FROM mem")
    assert "guard_errors" in raw
    assert "quarantined" in raw


def test_write_gate_strict_raises(tmp_path, monkeypatch):
    """En modo estricto el guard rechaza la escritura con WHAT/WHY/WHERE."""
    monkeypatch.setenv("SWARMIND_MEMORY_GUARD_STRICT", "1")
    guard = MemoryGuard({"mem": SCHEMA})
    store = RuscaDBStore(db_path=str(tmp_path / "strict.db"), memory_guard=guard)
    store.create_collection("mem")
    try:
        with pytest.raises(ValueError) as excinfo:
            store.insert("mem", [[1.0, 0.0]], [{"text": "sin tier"}])
        message = str(excinfo.value)
        assert "write_bloqueado" in message
        assert "guard_validation" in message
    finally:
        store.close()


def test_write_gate_absent_keeps_default_behavior(store):
    """Sin guard inyectado el insert no valida (backward compatible)."""
    ids = store.insert("mem", [[1.0, 0.0]], [{"cualquier": "campo"}])
    assert len(ids) == 1


def test_record_access_updates_last_accessed(store):
    """record_access incrementa access_count y fija last_accessed."""
    ids = store.insert(
        "mem", [[1.0, 0.0]], [{"trust_tier": "user_stated"}], texts=["nota"]
    )
    stamp = "2026-10-29T12:00:00+00:00"
    assert store.record_access("mem", ids, now=stamp) == 1
    raw = store.execute("SELECT * FROM mem")
    assert "last_accessed" in raw
    assert "access_count" in raw
    assert stamp in raw


def test_record_access_then_recency_uses_access_time(store):
    """Tras record_access, el decaimiento usa last_accessed (memoria rejuvenece)."""
    old = "2026-01-01T00:00:00+00:00"
    ids = store.insert(
        "mem",
        [[1.0, 0.0]],
        [{"trust_tier": "user_stated"}],
        texts=["memoria antigua"],
        now=old,
    )
    fresh = store.insert(
        "mem",
        [[0.0, 1.0]],
        [{"trust_tier": "user_stated"}],
        texts=["memoria nueva"],
    )
    assert len(ids) == 1 and len(fresh) == 1
    before = store.search("mem", [1.0, 0.0], top_k=5, half_life_days=30)
    assert before[0]["text"] == "memoria nueva"
    store.record_access("mem", ids)
    after = store.search("mem", [1.0, 0.0], top_k=5, half_life_days=30)
    assert after[0]["text"] == "memoria antigua"


def test_governance_columns_are_declared(store):
    """El esquema base declara las columnas de gobernanza indexables."""
    from harness.memory_rag.ruscadb_store import _SCHEMA

    names = {column["name"] for column in _SCHEMA}
    assert {
        "source",
        "trust_tier",
        "session_id",
        "derived_from",
        "write_gate_verdict",
    } <= names


def test_insert_writes_governance_columns(store):
    """El insert puebla las columnas (no solo el JSON de metadata)."""
    store.insert(
        "mem",
        [[1.0, 0.0]],
        [
            {
                "trust_tier": "user_stated",
                "session_id": "ses-42",
                "derived_from": "doc-9",
            }
        ],
        texts=["contenido"],
    )
    raw = store.execute("SELECT * FROM mem")
    assert "ses-42" in raw
    assert "doc-9" in raw
    assert "user_stated" in raw
    assert "allowed" in raw


def test_record_access_unknown_ids_is_noop(store):
    """Ids inexistentes no lanzan y devuelven 0."""
    assert store.record_access("mem", ["no-existe"]) == 0
