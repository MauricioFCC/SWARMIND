"""Tests para GraphRAGRetriever (frontier: arXiv:2410.05779 / 2404.16130)."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.memory_rag.graph_rag_retriever import GraphRAGRetriever


class _FakeStore:
    """Doble del store con resultados controlados."""

    def __init__(self, seeds, graph=None):
        self._seeds = seeds
        self._graph = graph or []

    def full_text_search(self, collection, query, top_k=10):
        return list(self._seeds)

    def graph_traverse(self, collection, depth=2, start=None):
        return list(self._graph)

    def __repr__(self):
        return "_FakeStore"


def test_dual_level_fuses_local_and_graph():
    seeds = [{"id": "a", "text": "raiz", "metadata": {}}]
    graph = [{"id": "a", "text": "raiz"}, {"id": "b", "text": "vecino"}]
    retriever = GraphRAGRetriever(_FakeStore(seeds, graph))
    results = retriever.retrieve("raiz", top_k=5)
    ids = [item["id"] for item in results]
    assert set(ids) == {"a", "b"}
    assert results[0]["id"] == "a"
    assert results[0]["local_rank"] == 1
    assert results[0]["graph_rank"] >= 1


def test_graph_only_result_has_zero_local_rank():
    seeds = [{"id": "a", "text": "raiz", "metadata": {}}]
    graph = [{"id": "b", "text": "vecino"}]
    retriever = GraphRAGRetriever(_FakeStore(seeds, graph))
    results = retriever.retrieve("raiz")
    by_id = {item["id"]: item for item in results}
    assert by_id["b"]["local_rank"] == 0
    assert by_id["b"]["graph_rank"] == 1


def test_empty_query_returns_empty():
    retriever = GraphRAGRetriever(_FakeStore([]))
    assert retriever.retrieve("   ", top_k=3) == []
    assert retriever.retrieve("x", top_k=0) == []


def test_empty_graph_degrades_to_local_only():
    retriever = GraphRAGRetriever(_FakeStore([{"id": "a"}], graph=[]))
    results = retriever.retrieve("x")
    assert [item["id"] for item in results] == ["a"]
    assert results[0]["graph_rank"] == 0


def test_store_errors_are_contained():
    class _Broken(_FakeStore):
        def graph_traverse(self, collection, depth=2, start=None):
            raise RuntimeError("boom")

    retriever = GraphRAGRetriever(_Broken([{"id": "a"}]))
    results = retriever.retrieve("x")
    assert [item["id"] for item in results] == ["a"]


def _rusca_available() -> bool:
    try:
        from harness.memory_rag.ruscadb import load_library

        load_library()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _rusca_available(), reason="RuscaDB C-ABI dll not available")
def test_graph_rag_integration_with_ruscadb():
    from harness.memory_rag.ruscadb_store import RuscaDBStore

    store = RuscaDBStore(db_path=os.path.join(tempfile.mkdtemp(), "g.db"))
    try:
        root = store.insert("nodes", [[0.0]], [{"text": "raiz del sistema"}])[0]
        store.insert(
            "nodes",
            [[0.0]],
            [{"text": "nodo hijo"}],
            edges=[[{"label": "link", "target": root}]],
        )
        retriever = GraphRAGRetriever(store, collection="nodes", depth=2)
        results = retriever.retrieve("raiz", top_k=5)
        texts = {item.get("text") for item in results}
        assert "raiz del sistema" in texts
        assert "nodo hijo" in texts
    finally:
        store.close()
