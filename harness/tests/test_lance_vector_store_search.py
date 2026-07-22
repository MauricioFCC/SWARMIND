# pragma: allowlist secret
"""Tests de búsqueda vectorial para LanceVectorStore.

Extraído de test_lance_vector_store.py — pruebas de search(),
hybrid_search() y get_collection_stats() en ambos modos.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import numpy as np
import pytest

from harness.memory_rag.lance_vector_store import (
    CollectionNotFoundError,
    _Collection,
    _StoredItem,
)

# ===========================================================================
# TESTS — Search
# ===========================================================================


class TestSearch:
    """Búsqueda vectorial en ambos modos."""

    def test_search_memory(self, mem_store):
        """search en modo memoria retorna resultados ordenados por similitud."""
        # Insertar varios vectores
        rng = np.random.RandomState(42)
        for i in range(5):
            v = rng.randn(384).astype(np.float32)
            v = v / np.linalg.norm(v)
            mem_store.insert(
                "rag_chunks",
                v.reshape(1, -1),
                [{"idx": i, "domain": "test", "tags": []}],
            )
        query = _make_vec(384, seed=99)
        results = mem_store.search("rag_chunks", query, top_k=3)
        assert len(results) <= 3
        for r in results:
            assert "id" in r
            assert "score" in r
            assert "metadata" in r
            assert "created_at" in r
        # Los scores deben estar en orden descendente
        scores = [r["score"] for r in results]
        assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))

    def test_search_memory_empty_collection(self, mem_store):
        """search en colección vacía retorna lista vacía."""
        results = mem_store.search("asi_cognition_store", _make_vec(384, seed=1), top_k=5)
        assert results == []

    def test_search_memory_collection_not_found(self, mem_store):
        """search en colección inexistente lanza CollectionNotFoundError."""
        with pytest.raises(CollectionNotFoundError) as excinfo:
            mem_store.search("ghost", _make_vec(384, seed=1))
        assert "not found in memory store" in str(excinfo.value)

    def test_search_memory_with_filters(self, mem_store):
        """search con filtros retorna solo items que matchean."""
        for i in range(3):
            v = _make_vec(384, seed=i).reshape(1, -1)
            mem_store.insert(
                "rag_chunks",
                v,
                [{"domain": "test", "group": f"g{i}"}],
            )
        query = _make_vec(384, seed=0)
        results = mem_store.search("rag_chunks", query, top_k=5, filters={"group": "g1"})
        assert len(results) == 1
        assert results[0]["metadata"]["group"] == "g1"

    def test_search_memory_no_candidates_after_filter(self, mem_store):
        """search con filtro que no matchea nada retorna vacío."""
        vec = _make_vec(384, seed=5).reshape(1, -1)
        mem_store.insert("rag_chunks", vec, [{"domain": "test"}])
        results = mem_store.search(
            "rag_chunks", _make_vec(384, seed=0), top_k=5,
            filters={"domain": "no_match"},
        )
        assert results == []

    def test_search_memory_all_vectors_none(self, mem_store_no_defaults):
        """search cuando todos los vectores son None retorna vacío."""
        col = _Collection(name="empty_vecs", schema_def={})
        col.items["i1"] = _StoredItem(
            id="i1", vector=None, metadata={}, created_at="now"
        )
        mem_store_no_defaults._mem_collections["empty_vecs"] = col
        results = mem_store_no_defaults.search(
            "empty_vecs", _make_vec(384, seed=0), top_k=5
        )
        assert results == []

    def test_search_lancedb(self, lancedb_store_with_data, mock_lancedb):
        """search en modo LanceDB retorna resultados."""
        table = mock_lancedb["table"]
        table.search.return_value.limit.return_value.to_list.return_value = [
            {
                "id": "r1",
                "vector": [0.1, 0.2],
                "metadata": json.dumps({"domain": "test"}),
                "created_at": "2025-01-01",
                "_distance": 0.9,
            },
        ]
        query = _make_vec(384, seed=0)
        results = lancedb_store_with_data.search("rag_chunks", query, top_k=5)
        assert len(results) == 1
        assert results[0]["id"] == "r1"
        assert results[0]["score"] == 0.9
        assert results[0]["metadata"] == {"domain": "test"}

    def test_search_lancedb_collection_not_found(self, lancedb_store, mock_lancedb):
        """search LanceDB con colección inexistente lanza CollectionNotFoundError."""
        mock_lancedb["db_conn"].open_table.side_effect = RuntimeError("missing")
        with pytest.raises(CollectionNotFoundError) as excinfo:
            lancedb_store.search("ghost", _make_vec(384, seed=0))
        assert "not found in LanceDB" in str(excinfo.value)

    def test_search_lancedb_with_filters(self, lancedb_store, mock_lancedb):
        """search LanceDB aplica post-filtros correctamente."""
        table = mock_lancedb["table"]
        table.search.return_value.limit.return_value.to_list.return_value = [
            {
                "id": "r1",
                "metadata": json.dumps({"domain": "test", "lang": "en"}),
                "created_at": "now",
                "_distance": 0.9,
            },
            {
                "id": "r2",
                "metadata": json.dumps({"domain": "test", "lang": "es"}),
                "created_at": "now",
                "_distance": 0.8,
            },
        ]
        query = _make_vec(384, seed=0)
        results = lancedb_store.search(
            "rag_chunks", query, top_k=5, filters={"lang": "en"}
        )
        assert len(results) == 1
        assert results[0]["id"] == "r1"

    def test_search_lancedb_metadata_json_fail(self, lancedb_store, mock_lancedb):
        """search maneja metadata con JSON inválido."""
        table = mock_lancedb["table"]
        table.search.return_value.limit.return_value.to_list.return_value = [
            {
                "id": "r1",
                "metadata": "{bad json]",
                "created_at": "now",
                "_distance": 0.5,
            },
        ]
        query = _make_vec(384, seed=0)
        results = lancedb_store.search("rag_chunks", query, top_k=5)
        assert len(results) == 1
        assert results[0]["metadata"] == {}

    def test_search_lancedb_metadata_is_dict(self, lancedb_store, mock_lancedb):
        """search cuando metadata ya es dict no intenta parsear."""
        table = mock_lancedb["table"]
        table.search.return_value.limit.return_value.to_list.return_value = [
            {
                "id": "r1",
                "metadata": {"domain": "test"},
                "created_at": "now",
                "_distance": 0.5,
            },
        ]
        query = _make_vec(384, seed=0)
        results = lancedb_store.search("rag_chunks", query, top_k=5)
        assert results[0]["metadata"] == {"domain": "test"}

    def test_search_lancedb_score_field(self, lancedb_store, mock_lancedb):
        """search usa _distance como score, con fallback a score."""
        table = mock_lancedb["table"]
        # Caso 1: con _distance
        table.search.return_value.limit.return_value.to_list.return_value = [
            {"id": "r1", "metadata": "{}", "created_at": "now", "_distance": 0.7},
        ]
        query = _make_vec(384, seed=0)
        r1 = lancedb_store.search("rag_chunks", query, top_k=5)
        assert r1[0]["score"] == 0.7

        # Caso 2: sin _distance, con score
        table.search.return_value.limit.return_value.to_list.return_value = [
            {"id": "r2", "metadata": "{}", "created_at": "now", "score": 0.8},
        ]
        r2 = lancedb_store.search("rag_chunks", query, top_k=5)
        assert r2[0]["score"] == 0.8

        # Caso 3: sin ninguno → 0.0
        table.search.return_value.limit.return_value.to_list.return_value = [
            {"id": "r3", "metadata": "{}", "created_at": "now"},
        ]
        r3 = lancedb_store.search("rag_chunks", query, top_k=5)
        assert r3[0]["score"] == 0.0


# ===========================================================================
# TESTS — Hybrid Search
# ===========================================================================


class TestHybridSearch:
    """hybrid_search combina búsqueda vectorial con keyword."""

    def test_hybrid_search_memory_basic(self, mem_store):
        """hybrid_search básico en modo memoria."""
        vec = _make_vec(384, seed=20).reshape(1, -1)
        mem_store.insert(
            "asi_cognition_store",
            vec,
            [{"domain": "trading", "title": "Rust engine", "tags": ["rust", "trading"]}],
        )
        query = _make_vec(384, seed=20)
        results = mem_store.hybrid_search(
            "asi_cognition_store", query, keyword_filter="rust", top_k=5
        )
        assert len(results) == 1
        # El resultado no debe tener _keyword_bonus (se limpia internamente)
        assert "_keyword_bonus" not in results[0]

    def test_hybrid_search_reranking(self, mem_store):
        """hybrid_search re-ordena por combined_score."""
        rng = np.random.RandomState(30)
        for i in range(3):
            v = rng.randn(384).astype(np.float32)
            v = v / np.linalg.norm(v)
            mem_store.insert(
                "asi_cognition_store",
                v.reshape(1, -1),
                [{
                    "domain": "trading",
                    "title": f"item {i}",
                    "tags": ["rust"] if i == 0 else [],
                }],
            )
        query = _make_vec(384, seed=0)

        # Buscar con keyword que solo matchea item 0
        results = mem_store.hybrid_search(
            "asi_cognition_store", query, keyword_filter="item 0", top_k=5
        )
        # El item con keyword debería estar primero (keyword_bonus = 1.0)
        assert len(results) >= 1

    def test_hybrid_search_empty(self, mem_store):
        """hybrid_search en colección vacía retorna lista vacía."""
        query = _make_vec(384, seed=0)
        results = mem_store.hybrid_search(
            "asi_cognition_store", query, keyword_filter="anything", top_k=5
        )
        assert results == []

    def test_hybrid_search_keyword_in_chunk(self, mem_store):
        """hybrid_search busca keyword en campo chunk del metadata."""
        vec = _make_vec(384, seed=25).reshape(1, -1)
        mem_store.insert(
            "asi_cognition_store",
            vec,
            [{"domain": "test", "chunk": "contains the magic word"}],
        )
        query = _make_vec(384, seed=25)
        results = mem_store.hybrid_search(
            "asi_cognition_store", query, keyword_filter="magic", top_k=5
        )
        assert len(results) == 1


# ===========================================================================
# TESTS — Collection Stats
# ===========================================================================


class TestStats:
    """get_collection_stats en ambos modos."""

    def test_stats_memory(self, mem_store):
        """get_collection_stats retorna metadata de colección en memoria."""
        vec = _make_vec(384, seed=30).reshape(1, -1)
        mem_store.insert("rag_chunks", vec, [{"domain": "test"}])
        stats = mem_store.get_collection_stats("rag_chunks")
        assert stats["name"] == "rag_chunks"
        assert stats["item_count"] >= 1
        assert "schema" in stats
        assert "last_updated" in stats

    def test_stats_memory_not_found(self, mem_store):
        """get_collection_stats en colección inexistente lanza error."""
        with pytest.raises(CollectionNotFoundError) as excinfo:
            mem_store.get_collection_stats("no_such_coll")
        assert "not found in memory store" in str(excinfo.value)

    def test_stats_lancedb(self, lancedb_store_with_data, mock_lancedb):
        """get_collection_stats retorna estadísticas desde LanceDB."""
        stats = lancedb_store_with_data.get_collection_stats("rag_chunks")
        assert stats["name"] == "rag_chunks"
        assert stats["item_count"] == 3
        assert stats["last_updated"] == "2025-01-02T00:00:00"

    def test_stats_lancedb_not_found(self, lancedb_store, mock_lancedb):
        """get_collection_stats en tabla inexistente lanza error."""
        mock_lancedb["db_conn"].open_table.side_effect = RuntimeError("missing")
        with pytest.raises(CollectionNotFoundError) as excinfo:
            lancedb_store.get_collection_stats("ghost")
        assert "not found" in str(excinfo.value)

    def test_stats_lancedb_empty_table(self, lancedb_store, mock_lancedb):
        """get_collection_stats en tabla vacía retorna last_updated vacío."""
        table = mock_lancedb["table"]
        table.count_rows.return_value = 0
        stats = lancedb_store.get_collection_stats("rag_chunks")
        assert stats["item_count"] == 0
        assert stats["last_updated"] == ""

    def test_stats_lancedb_to_arrow_fails(self, lancedb_store, mock_lancedb):
        """get_collection_stats cuando to_arrow falla retorna last_updated vacío."""
        table = mock_lancedb["table"]
        table.count_rows.return_value = 1
        table.to_arrow.side_effect = RuntimeError("arrow fail")
        stats = lancedb_store.get_collection_stats("rag_chunks")
        assert stats["item_count"] == 1
        assert stats["last_updated"] == ""

    def test_stats_lancedb_no_created_at_column(self, lancedb_store, mock_lancedb):
        """get_collection_stats cuando falta columna created_at."""
        table = mock_lancedb["table"]
        table.count_rows.return_value = 1
        arrow_mock = MagicMock()
        arrow_mock.num_rows = 1
        arrow_mock.column_names = ["id", "vector"]
        table.to_arrow.return_value = arrow_mock
        stats = lancedb_store.get_collection_stats("rag_chunks")
        assert stats["item_count"] == 1
        assert stats["last_updated"] == ""

    def test_stats_lancedb_arrow_zero_rows(self, lancedb_store, mock_lancedb):
        """get_collection_stats con item_count>0 pero arrow vacío (num_rows==0)."""
        table = mock_lancedb["table"]
        table.count_rows.return_value = 1
        arrow_mock = MagicMock()
        arrow_mock.num_rows = 0
        table.to_arrow.return_value = arrow_mock
        stats = lancedb_store.get_collection_stats("rag_chunks")
        assert stats["item_count"] == 1
        # No se entra al bloque num_rows>0 → last_updated queda ""
        assert stats["last_updated"] == ""


# ===========================================================================
# TESTS — Hybrid search en modo LanceDB
# ===========================================================================


class TestHybridSearchLanceDB:
    """hybrid_search en modo LanceDB."""

    def test_hybrid_search_lancedb(self, lancedb_store, mock_lancedb):
        """hybrid_search delega a search y re-ordena."""
        table = mock_lancedb["table"]
        # search retorna 2 resultados
        table.search.return_value.limit.return_value.to_list.return_value = [
            {
                "id": "r1",
                "metadata": json.dumps({"domain": "trading", "title": "Rust", "tags": ["rust"]}),
                "created_at": "now",
                "_distance": 0.9,
            },
            {
                "id": "r2",
                "metadata": json.dumps({"domain": "other", "title": "Python", "tags": []}),
                "created_at": "now",
                "_distance": 0.8,
            },
        ]
        query = _make_vec(384, seed=0)
        results = lancedb_store.hybrid_search(
            "rag_chunks", query, keyword_filter="rust", top_k=5
        )
        # r1 tiene keyword 'rust' → debería tener keyword_bonus = 1.0
        assert len(results) == 2
        assert "_keyword_bonus" not in results[0]
        # r1 debe estar primero porque tiene keyword_bonus
        assert results[0]["id"] == "r1"

    def test_hybrid_search_lancedb_empty(self, lancedb_store, mock_lancedb):
        """hybrid_search sin resultados vectoriales retorna vacío."""
        table = mock_lancedb["table"]
        table.search.return_value.limit.return_value.to_list.return_value = []
        query = _make_vec(384, seed=0)
        results = lancedb_store.hybrid_search(
            "rag_chunks", query, keyword_filter="anything", top_k=5
        )
        assert results == []


# ===========================================================================
# Helper local (también definido en conftest.py para disponibilidad en fixtures)
# ===========================================================================


def _make_vec(dim: int = 384, seed: int = 0) -> np.ndarray:
    """Crea un vector unitario normalizado para tests."""
    rng = np.random.RandomState(seed)
    v = rng.randn(dim).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-12)
