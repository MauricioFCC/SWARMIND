"""Tests del wrapper async de RuscaDB (Spec ruscadb-async-io)."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from harness.memory_rag.async_ruscadb import AsyncRuscaDBStore
from harness.memory_rag.hybrid_retriever import HybridRetriever
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
def async_store(tmp_path):
    """Wrapper async sobre un store aislado por test."""
    store = RuscaDBStore(db_path=str(tmp_path / "async.db"))
    store.create_collection("mem")
    wrapper = AsyncRuscaDBStore(store)
    yield wrapper
    asyncio.run(wrapper.close())


def test_async_insert_and_search(async_store):
    """insert/search delegan en hilos y devuelven el mismo contrato."""

    async def scenario() -> list[dict]:
        ids = await async_store.insert(
            "mem", np.ones((1, 4), dtype=np.float32), [{"k": "v"}], texts=["hola"]
        )
        assert len(ids) == 1
        return await async_store.search("mem", [1.0, 1.0, 1.0, 1.0], top_k=3)

    results = asyncio.run(scenario())
    assert results
    assert results[0]["metadata"]["k"] == "v"


def test_async_hybrid_and_fts(async_store):
    """hybrid_search y full_text_search funcionan en modo async."""

    async def scenario() -> tuple[list[dict], list[dict]]:
        await async_store.insert(
            "mem", [[1.0, 0.0]], [{"k": 1}], texts=["gato domestico"]
        )
        hybrid = await async_store.hybrid_search(
            "mem", [1.0, 0.0], query_text="gato", top_k=3
        )
        fts = await async_store.full_text_search("mem", "gato", top_k=3)
        return hybrid, fts

    hybrid, fts = asyncio.run(scenario())
    assert isinstance(hybrid, list)
    assert isinstance(fts, list)


def test_async_delete_and_execute(async_store):
    """delete/execute se ejecutan sin bloquear el loop."""

    async def scenario() -> tuple[int, str]:
        ids = await async_store.insert("mem", [[1.0, 0.0]], [{"k": 1}])
        removed = await async_store.delete("mem", ids)
        raw = await async_store.execute("SELECT COUNT(*) as n FROM mem")
        return removed, raw

    removed, raw = asyncio.run(scenario())
    assert removed == 1
    assert "n" in raw


def test_async_context_manager(tmp_path):
    """``async with`` cierra el store subyacente al salir."""
    store = RuscaDBStore(db_path=str(tmp_path / "ctx.db"))

    async def scenario() -> type:
        async with AsyncRuscaDBStore(store) as wrapper:
            assert wrapper.store is store
        return type(store)

    assert asyncio.run(scenario()) is RuscaDBStore


def test_from_path_builds_store(tmp_path):
    """from_path construye el store subyacente y lo expone."""

    async def scenario() -> bool:
        wrapper = AsyncRuscaDBStore.from_path(str(tmp_path / "from_path.db"))
        try:
            return isinstance(wrapper.store, RuscaDBStore)
        finally:
            await wrapper.close()

    assert asyncio.run(scenario()) is True


def test_hybrid_retriever_aretrieve(tmp_path):
    """HybridRetriever.aretrieve ejecuta el retrieval en un hilo."""
    store = RuscaDBStore(db_path=str(tmp_path / "hybrid.db"))
    store.create_collection("mem")
    store.insert("mem", [[1.0, 0.0]], [{"k": 1}], texts=["gato domestico"])

    class _FTS:
        def search(self, query: str, top_k: int = 5) -> list[dict]:
            return []

    retriever = HybridRetriever(
        vector_store=store,
        fts_search=_FTS(),
        embed_fn=lambda _text: np.array([1.0, 0.0], dtype=np.float32),
        collection="mem",
    )
    try:
        results = asyncio.run(retriever.aretrieve("gato", top_k=3))
        assert results
        assert results[0].doc_id
    finally:
        store.close()
