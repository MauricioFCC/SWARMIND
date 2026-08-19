"""test_hybrid_retriever.py — Tests del RAG hibrido con fusion RRF."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from harness.memory_rag.hybrid_retriever import (
    DENSE_WEIGHT,
    SPARSE_WEIGHT,
    HybridResult,
    HybridRetriever,
)


class FakeVectorStore:
    """Doble del LanceVectorStore con resultados deterministicos."""

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = results

    def search(
        self, collection: str, query_vector: np.ndarray, top_k: int = 5
    ) -> list[dict[str, Any]]:
        return self._results[:top_k]


class FakeFTSSearch:
    """Doble del FTSSearch con resultados deterministicos."""

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = results

    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        return self._results[:top_k]


def _embed(text: str) -> np.ndarray:
    """Embedding fake determinista (basado en longitud)."""
    return np.zeros((1, 8), dtype=np.float32) + float(len(text))


def _dense_results() -> list[dict[str, Any]]:
    """Resultados densos de ejemplo (doc_a primero, doc_b segundo)."""
    return [
        {"id": "doc_a", "score": 0.9, "metadata": {"chunk": "alpha"}},
        {"id": "doc_b", "score": 0.7, "metadata": {"chunk": "beta"}},
        {"id": "doc_c", "score": 0.5, "metadata": {"chunk": "gamma"}},
    ]


def _sparse_results() -> list[dict[str, Any]]:
    """Resultados dispersos de ejemplo (doc_b primero, doc_a ausente)."""
    return [
        {"id": "doc_b", "score": 8.0, "metadata": {"chunk": "beta"}},
        {"id": "doc_d", "score": 5.0, "metadata": {"chunk": "delta"}},
    ]


def test_retrieve_fuses_rankings() -> None:
    """Un documento presente en ambos rankings puntua mas alto."""
    hybrid = HybridRetriever(
        vector_store=FakeVectorStore(_dense_results()),
        fts_search=FakeFTSSearch(_sparse_results()),
        embed_fn=_embed,
    )
    results = hybrid.retrieve("alpha beta", top_k=5)
    by_id = {item.doc_id: item for item in results}
    # doc_b aparece en ambos rankings -> mayor score RRF que doc_a (solo denso)
    assert by_id["doc_b"].score > by_id["doc_a"].score
    assert by_id["doc_b"].dense_rank == 2
    assert by_id["doc_b"].sparse_rank == 1
    assert by_id["doc_a"].sparse_rank == 0


def test_retrieve_returns_sorted_desc() -> None:
    """Los resultados se ordenan por score RRF descendente."""
    hybrid = HybridRetriever(
        vector_store=FakeVectorStore(_dense_results()),
        fts_search=FakeFTSSearch(_sparse_results()),
        embed_fn=_embed,
    )
    results = hybrid.retrieve("query", top_k=5)
    scores = [item.score for item in results]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_respects_top_k() -> None:
    """top_k limita el numero de resultados devueltos."""
    hybrid = HybridRetriever(
        vector_store=FakeVectorStore(_dense_results()),
        fts_search=FakeFTSSearch(_sparse_results()),
        embed_fn=_embed,
    )
    results = hybrid.retrieve("query", top_k=2)
    assert len(results) == 2


def test_retrieve_invalid_top_k_raises() -> None:
    """top_k no positivo -> ValueError con WHAT/WHY/WHERE."""
    hybrid = HybridRetriever(
        vector_store=FakeVectorStore([]),
        fts_search=FakeFTSSearch([]),
        embed_fn=_embed,
    )
    with pytest.raises(ValueError, match="WHAT:"):
        hybrid.retrieve("query", top_k=0)


def test_retrieve_empty_query_raises() -> None:
    """Query vacia -> ValueError."""
    hybrid = HybridRetriever(
        vector_store=FakeVectorStore([]),
        fts_search=FakeFTSSearch([]),
        embed_fn=_embed,
    )
    with pytest.raises(ValueError, match="WHAT:"):
        hybrid.retrieve("   ")


def test_retrieve_no_results() -> None:
    """Sin resultados en ninguna fuente -> lista vacia."""
    hybrid = HybridRetriever(
        vector_store=FakeVectorStore([]),
        fts_search=FakeFTSSearch([]),
        embed_fn=_embed,
    )
    assert hybrid.retrieve("query") == []


def test_fuse_single_rankings() -> None:
    """Documentos solo en un ranking conservan su contribucion RRF."""
    fused = HybridRetriever._fuse(_dense_results()[:1], _sparse_results()[1:])
    by_id = {item.doc_id: item for item in fused}
    assert by_id["doc_a"].dense_rank == 1
    assert by_id["doc_d"].sparse_rank == 1
    assert by_id["doc_a"].sparse_rank == 0


def test_fuse_ignores_items_without_id() -> None:
    """Items sin id se ignoran en la fusion."""
    dense = [{"score": 0.9, "metadata": {}}]
    fused = HybridRetriever._fuse(dense, [])
    assert fused == []


def test_hybrid_result_dataclass() -> None:
    """HybridResult es una dataclass con los campos esperados."""
    result = HybridResult(doc_id="x", score=0.5, dense_rank=1, sparse_rank=2)
    assert result.doc_id == "x"
    assert result.score == pytest.approx(0.5)
    assert result.dense_rank == 1
    assert result.sparse_rank == 2
    assert result.metadata == {}


def test_weights_exported() -> None:
    """Los pesos denso/disperso se exportan para consumidores."""
    assert DENSE_WEIGHT == 0.5
    assert SPARSE_WEIGHT == 0.5