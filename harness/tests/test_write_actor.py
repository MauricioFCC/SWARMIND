"""Tests del actor de escritura single-writer (Spec ruscadb-async-io)."""

from __future__ import annotations

import asyncio
import queue

import pytest

from harness.memory_rag.async_ruscadb import (
    AsyncRuscaDBStore,
    MemoryBackpressureError,
    WriteActor,
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


@pytest.fixture
def store(tmp_path):
    """Store RuscaDB aislado por test."""
    s = RuscaDBStore(db_path=str(tmp_path / "actor.db"))
    s.create_collection("mem")
    yield s
    s.close()


def test_actor_runs_tasks_in_order(store):
    """El actor ejecuta las tareas en el hilo dedicado y devuelve resultados."""
    actor = WriteActor(store)
    try:
        result = actor.submit(lambda value: value * 2, 21)
        assert result == 42
        assert actor.pending == 0
    finally:
        actor.close()


def test_actor_backpressure_raises_typed_error(store, monkeypatch):
    """Cola llena -> MemoryBackpressureError (nunca bloquea el loop)."""
    actor = WriteActor(store, queue_size=1)
    try:
        def _full(_item):
            raise queue.Full

        monkeypatch.setattr(actor._queue, "put_nowait", _full)
        with pytest.raises(MemoryBackpressureError) as excinfo:
            actor.submit(lambda: None)
        assert "cola_llena" in str(excinfo.value)
    finally:
        actor.close()


def test_actor_close_is_idempotent(store):
    """close() se puede llamar dos veces sin excepciones."""
    actor = WriteActor(store)
    actor.close()
    actor.close()
    with pytest.raises(RuntimeError):
        actor.submit(lambda: None)


def test_actor_rejects_invalid_queue_size(store):
    """queue_size <= 0 es error de programacion."""
    with pytest.raises(ValueError):
        WriteActor(store, queue_size=0)


def test_async_store_with_actor_inserts(store):
    """AsyncRuscaDBStore(write_actor=True) escribe por el actor."""
    wrapper = AsyncRuscaDBStore(store, write_actor=True)

    async def scenario() -> tuple[list[str], int]:
        ids = await wrapper.insert("mem", [[1.0, 0.0]], [{"k": 1}], texts=["hola"])
        removed = await wrapper.delete("mem", ids)
        await wrapper.close()
        return ids, removed

    ids, removed = asyncio.run(scenario())
    assert len(ids) == 1
    assert removed == 1
    assert wrapper.write_actor is not None


def test_async_store_without_actor_has_none(store):
    """Sin write_actor no se crea hilo extra."""
    wrapper = AsyncRuscaDBStore(store)
    assert wrapper.write_actor is None
    asyncio.run(wrapper.close())
