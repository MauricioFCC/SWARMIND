"""Tests del actor de escritura single-writer (Spec ruscadb-async-io)."""

from __future__ import annotations

import asyncio
import queue

import pytest

from harness.memory_rag.async_ruscadb import (
    AsyncRuscaDBStore,
    MemoryBackpressureError,
    WriteActor,
    WriteBatcher,
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


class _CountingStore:
    """Spy que cuenta llamadas a ``insert`` y delega en el store real."""

    def __init__(self, real):
        self._real = real
        self.insert_calls = 0

    def insert(self, collection, vectors, metadata, **kwargs):
        self.insert_calls += 1
        return self._real.insert(collection, vectors, metadata, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_batcher_coalesces_concurrent_inserts(store):
    """Dos inserts concurrentes viajan al motor en una sola llamada."""
    spy = _CountingStore(store)
    batcher = WriteBatcher(spy, max_batch=2, max_delay=1.0)
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(batcher.submit, "mem", [[1.0, 0.0]], [{"k": 1}])
        second = pool.submit(batcher.submit, "mem", [[0.0, 1.0]], [{"k": 2}])
        ids_first = first.result(timeout=5)
        ids_second = second.result(timeout=5)
    assert spy.insert_calls == 1
    assert len(ids_first) == 1 and len(ids_second) == 1
    assert ids_first[0] != ids_second[0]


def test_batcher_flushes_single_request_after_delay(store):
    """Un insert solitario no se queda colgado: flush por max_delay."""
    spy = _CountingStore(store)
    batcher = WriteBatcher(spy, max_batch=8, max_delay=0.001)
    ids = batcher.submit("mem", [[1.0, 0.0]], [{"k": 1}])
    assert len(ids) == 1
    assert spy.insert_calls == 1
    assert batcher.pending == 0


def test_batcher_flush_sends_pending(store):
    """flush() fuerza el envio de un lote incompleto."""
    spy = _CountingStore(store)
    batcher = WriteBatcher(spy, max_batch=8, max_delay=1.0)
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(batcher.submit, "mem", [[1.0, 0.0]], [{"k": 1}])
        while batcher.pending == 0:
            pass
        assert batcher.flush() == 1
        assert len(future.result(timeout=5)) == 1
    assert spy.insert_calls == 1


def test_async_store_with_batching_inserts(store):
    """AsyncRuscaDBStore(batch_size) inserta correctamente y cierra limpio."""
    spy = _CountingStore(store)
    wrapper = AsyncRuscaDBStore(spy, batch_size=2)

    async def scenario() -> list[str]:
        first, second = await asyncio.gather(
            wrapper.insert("mem", [[1.0, 0.0]], [{"k": 1}]),
            wrapper.insert("mem", [[0.0, 1.0]], [{"k": 2}]),
        )
        await wrapper.close()
        return first + second

    ids = asyncio.run(scenario())
    assert len(ids) == 2
    assert len(set(ids)) == 2
