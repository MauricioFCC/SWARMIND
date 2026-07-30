"""
Tests para FTSSearch — full-text search sobre memoria (inspirado en FTS5).

Cubre: inicialización, indexado, búsqueda (FTS5 y fallback memoria),
ranking, snippets, delete, clear, get_stats, edge cases y manejo de errores.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from harness.memory_rag.fts_search import STOPWORDS, FTSSearch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fts_memory():
    """FTSSearch en modo memoria (sin FTS5)."""
    with patch("harness.memory_rag.fts_search.FTSSearch._init_sqlite_fts") as mock_init:
        mock_init.return_value = False
        fts = FTSSearch(db_path=Path("/tmp/test_fts_memory.db"))
        yield fts


@pytest.fixture
def fts_with_docs(fts_memory):
    """FTSSearch con documentos pre-indexados en memoria."""
    fts_memory.index("doc1", "sistema de trading con Rust y Python", {"domain": "trading"})
    fts_memory.index("doc2", "arquitectura hexagonal en Go", {"domain": "backend"})
    fts_memory.index("doc3", "machine learning con Python para trading", {"domain": "ml"})
    fts_memory.index("doc4", "El gato saltó sobre el perro", {"domain": "test"})
    return fts_memory


@pytest.fixture
def fts_fts5():
    """FTSSearch en modo FTS5 mockeado."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    # Configurar mock del cursor
    mock_conn.execute.return_value = mock_cursor
    mock_conn.cursor.return_value = mock_cursor

    with patch("harness.memory_rag.fts_search.FTSSearch._init_sqlite_fts") as mock_init:
        mock_init.return_value = True
        with patch("harness.memory_rag.fts_search.sqlite3.connect") as mock_connect:
            mock_connect.return_value = mock_conn
            fts = FTSSearch(db_path=Path("/tmp/test_fts5.db"))
            # Forzar el estado FTS5
            fts._fts_available = True
            fts._conn = mock_conn
            yield fts


# ---------------------------------------------------------------------------
# Tests: Initialization
# ---------------------------------------------------------------------------


class TestInitialization:
    """Tests de inicialización del FTSSearch."""

    def test_init_default_path(self):
        """FTSSearch debe usar FTS_DB_PATH por defecto."""
        with patch("harness.memory_rag.fts_search.FTSSearch._init_sqlite_fts") as mock_init:
            mock_init.return_value = False
            from harness.memory_rag.fts_search import FTS_DB_PATH
            fts = FTSSearch()
            assert fts.db_path == FTS_DB_PATH

    def test_init_memory_fallback(self, fts_memory):
        """Sin FTS5, debe usar modo memoria."""
        assert not fts_memory._fts_available
        assert fts_memory._conn is None

    def test_init_fts5_mode(self, fts_fts5):
        """Con FTS5 disponible, debe usar SQLite."""
        assert fts_fts5._fts_available
        assert fts_fts5._conn is not None

    def test_init_empty_mem_index(self, fts_memory):
        """Índice en memoria debe iniciar vacío."""
        assert fts_memory._mem_index == {}


# ---------------------------------------------------------------------------
# Tests: Indexing
# ---------------------------------------------------------------------------


class TestIndexing:
    """Tests para indexado de documentos."""

    def test_index_memory_success(self, fts_memory):
        """index() en modo memoria debe retornar True."""
        result = fts_memory.index("doc1", "contenido de prueba", {"key": "val"})
        assert result
        assert "doc1" in fts_memory._mem_index

    def test_index_memory_content(self, fts_memory):
        """index() debe almacenar contenido y metadata."""
        meta = {"domain": "test", "source": "manual"}
        fts_memory.index("doc1", "contenido", meta)
        content, stored_meta = fts_memory._mem_index["doc1"]
        assert content == "contenido"
        assert stored_meta == meta

    def test_index_batch(self, fts_memory):
        """index_batch() debe indexar múltiples documentos."""
        docs = [
            ("d1", "texto 1", {"k": "v1"}, "general"),
            ("d2", "texto 2", {"k": "v2"}, "general"),
        ]
        count = fts_memory.index_batch(docs)
        assert count == 2
        assert "d1" in fts_memory._mem_index
        assert "d2" in fts_memory._mem_index

    def test_index_batch_empty(self, fts_memory):
        """index_batch() con lista vacía debe retornar 0."""
        count = fts_memory.index_batch([])
        assert count == 0

    def test_index_fts5_success(self, fts_fts5):
        """index() en modo FTS5 debe ejecutar SQL."""
        fts_fts5.index("doc1", "contenido fts", {"source": "test"}, "general")
        # Debe ejecutar INSERT en documents_fts y doc_metadata
        assert fts_fts5._conn.execute.call_count >= 2

    def test_index_fts5_failure_logs_warning(self, fts_fts5, caplog):
        """Si FTS5 index falla, debe loguear warning."""
        fts_fts5._conn.execute.side_effect = Exception("DB error")
        with caplog.at_level(logging.WARNING):
            result = fts_fts5.index("doc1", "contenido", {}, "general")
            assert not result
        assert any("FTS index failed" in msg for msg in caplog.messages)


# ---------------------------------------------------------------------------
# Tests: Search (Memory mode)
# ---------------------------------------------------------------------------


class TestSearchMemory:
    """Tests de búsqueda en modo memoria."""

    def test_search_basic(self, fts_with_docs):
        """Búsqueda básica debe encontrar documentos relevantes."""
        results = fts_with_docs.search("trading Rust")
        assert len(results) >= 1
        ids = [r["id"] for r in results]
        assert "doc1" in ids

    def test_search_ranking(self, fts_with_docs):
        """Resultados deben ordenarse por score descendente."""
        results = fts_with_docs.search("Python trading")
        assert len(results) >= 2
        scores = [r["score"] for r in results]
        assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))

    def test_search_no_results(self, fts_with_docs):
        """Búsqueda sin match debe retornar lista vacía."""
        results = fts_with_docs.search("zzzxyz_nonexistent_12345")
        assert results == []

    def test_search_empty_query(self, fts_with_docs):
        """Query vacía debe retornar lista vacía."""
        results = fts_with_docs.search("")
        assert results == []

    def test_search_short_terms_filtered(self, fts_with_docs):
        """Términos de <= 2 caracteres deben filtrarse."""
        results = fts_with_docs.search("a an the")
        # Solo stopwords y términos cortos
        assert results == []

    def test_search_domain_filter(self, fts_with_docs):
        """Filtro por dominio debe retornar solo documentos de ese dominio."""
        results = fts_with_docs.search("trading", domain_filter="trading")
        assert len(results) >= 1
        for r in results:
            assert r["metadata"].get("domain") == "trading"

    def test_search_domain_filter_no_match(self, fts_with_docs):
        """Filtro por dominio sin match debe retornar lista vacía."""
        results = fts_with_docs.search("trading", domain_filter="nonexistent_domain_xyz")
        assert results == []

    def test_search_top_k(self, fts_with_docs):
        """Parámetro top_k debe limitar resultados."""
        results = fts_with_docs.search("Python", top_k=1)
        assert len(results) <= 1

    def test_search_stopwords_ignored(self, fts_memory):
        """Stopwords no deben afectar la búsqueda."""
        fts_memory.index("d1", "desarrollo de software con Rust", {})
        results = fts_memory.search("the a de con")  # solo stopwords
        assert results == []


# ---------------------------------------------------------------------------
# Tests: Search (FTS5 mode)
# ---------------------------------------------------------------------------


class TestSearchFTS5:
    """Tests de búsqueda en modo FTS5 mockeado."""

    def test_fts5_search_formats_query(self, fts_fts5):
        """_search_fts debe formatear query con OR y quotes."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        fts_fts5._conn.execute.return_value = mock_cursor

        fts_fts5._search_fts("trading Rust", top_k=10, domain_filter=None)
        # Verificar que la query incluye términos sin stopwords
        call_args = fts_fts5._conn.execute.call_args
        _sql, params = call_args[0]
        assert "trading" in params[0] or "Rust" in params[0]

    def test_fts5_search_with_domain_filter(self, fts_fts5):
        """_search_fts debe agregar domain filter a la SQL."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        fts_fts5._conn.execute.return_value = mock_cursor

        fts_fts5._search_fts("test", top_k=5, domain_filter="backend")
        sql = fts_fts5._conn.execute.call_args[0][0]
        assert "d.domain = ?" in sql

    def test_fts5_search_empty_query(self, fts_fts5):
        """Query con solo stopwords debe retornar []."""
        results = fts_fts5._search_fts("the a an", top_k=10, domain_filter=None)
        assert results == []

    def test_fts5_search_failure_returns_empty(self, fts_fts5):
        """Si FTS5 search lanza excepción, debe retornar []."""
        fts_fts5._conn.execute.side_effect = Exception("Search error")
        results = fts_fts5._search_fts("trading", top_k=10, domain_filter=None)
        assert results == []

    def test_fts5_search_parses_results(self, fts_fts5):
        """_search_fts debe parsear filas correctamente."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": "doc1", "domain": "trading", "content": "trading con Rust",
             "score": 10.0, "metadata": json.dumps({"source": "test"})},
        ]
        fts_fts5._conn.execute.return_value = mock_cursor

        results = fts_fts5._search_fts("trading", top_k=10, domain_filter=None)
        assert len(results) == 1
        assert results[0]["id"] == "doc1"
        assert results[0]["score"] > 0


# ---------------------------------------------------------------------------
# Tests: Snippet generation
# ---------------------------------------------------------------------------


class TestMakeSnippet:
    """Tests para _make_snippet (generación de snippets con highlighting)."""

    def test_snippet_basic(self):
        """Debe generar snippet con contexto alrededor del match."""
        text = "El sistema de trading con Rust es muy rápido"
        snippet = FTSSearch._make_snippet(text, "trading")
        assert "**trading**" in snippet

    def test_snippet_no_match(self):
        """Sin match, debe retornar inicio del texto."""
        text = "Este es un texto de prueba sin coincidencias"
        snippet = FTSSearch._make_snippet(text, "zzzxyz_nonexistent")
        assert snippet.startswith("Este")

    def test_snippet_empty_text(self):
        """Con texto vacío, debe retornar ''."""
        snippet = FTSSearch._make_snippet("", "query")
        assert snippet == ""

    def test_snippet_empty_query(self):
        """Con query vacía, debe retornar texto truncado."""
        snippet = FTSSearch._make_snippet("Hola mundo", "")
        assert snippet == "Hola mundo"

    def test_snippet_highlight_all_terms(self):
        """Debe resaltar todos los términos de la query."""
        text = "sistema de trading con Python y Rust"
        snippet = FTSSearch._make_snippet(text, "trading Python")
        assert "**trading**" in snippet
        # Los términos se pasan a lowercase internamente
        assert "**python**" in snippet.lower()

    def test_snippet_case_insensitive(self):
        """El resaltado debe ser case-insensitive."""
        text = "TRADING de alta frecuencia"
        snippet = FTSSearch._make_snippet(text, "trading")
        assert "**trading**" in snippet.lower() or "**TRADING**" in snippet


# ---------------------------------------------------------------------------
# Tests: Delete, Clear, Stats
# ---------------------------------------------------------------------------


class TestManagement:
    """Tests para delete, clear y get_stats."""

    def test_delete_memory_success(self, fts_with_docs):
        """delete() en modo memoria debe eliminar el documento."""
        result = fts_with_docs.delete("doc1")
        assert result
        assert "doc1" not in fts_with_docs._mem_index

    def test_delete_memory_not_found(self, fts_memory):
        """delete() de documento inexistente debe retornar False."""
        result = fts_memory.delete("nonexistent_doc_xyz")
        assert not result

    def test_delete_fts5_success(self, fts_fts5):
        """delete() en modo FTS5 debe ejecutar DELETE."""
        result = fts_fts5.delete("doc1")
        assert result
        assert fts_fts5._conn.execute.call_count >= 2

    def test_clear_memory(self, fts_with_docs):
        """clear() debe eliminar todos los documentos."""
        assert len(fts_with_docs._mem_index) > 0
        fts_with_docs.clear()
        assert fts_with_docs._mem_index == {}

    def test_clear_fts5(self, fts_fts5):
        """clear() en modo FTS5 debe ejecutar DELETE FROM."""
        fts_fts5.clear()
        # Debe ejecutar DELETE en ambas tablas
        assert fts_fts5._conn.execute.call_count >= 2

    def test_get_stats_memory(self, fts_memory):
        """get_stats() en modo memoria debe indicar backend memory."""
        stats = fts_memory.get_stats()
        assert stats["backend"] == "memory"
        assert stats["document_count"] == 0

    def test_get_stats_memory_with_docs(self, fts_with_docs):
        """get_stats() debe reflejar documentos indexados."""
        stats = fts_with_docs.get_stats()
        assert stats["document_count"] == 4

    def test_get_stats_fts5(self, fts_fts5):
        """get_stats() en modo FTS5 debe indicar backend fts5."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (5,)
        fts_fts5._conn.execute.return_value = mock_cursor

        stats = fts_fts5.get_stats()
        assert stats["backend"] == "fts5"


# ---------------------------------------------------------------------------
# Tests: Close
# ---------------------------------------------------------------------------


class TestClose:
    """Tests para close()."""

    def test_close_connection(self, fts_fts5):
        """close() debe cerrar la conexión SQLite."""
        conn = fts_fts5._conn
        fts_fts5.close()
        conn.close.assert_called_once()
        assert fts_fts5._conn is None

    def test_close_no_connection(self, fts_memory):
        """close() sin conexión no debe lanzar error."""
        fts_memory.close()
        assert True


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests de edge cases varios."""

    def test_stopwords_frozenset(self):
        """STOPWORDS debe ser un frozenset."""
        assert isinstance(STOPWORDS, frozenset)

    def test_index_duplicate_overwrites(self, fts_memory):
        """Indexar mismo doc_id debe sobrescribir."""
        fts_memory.index("doc1", "contenido original", {})
        fts_memory.index("doc1", "contenido nuevo", {})
        content, _ = fts_memory._mem_index["doc1"]
        assert content == "contenido nuevo"

    def test_search_fts5_all_stopwords(self, fts_fts5):
        """Query de solo stopwords en FTS5 debe retornar []."""
        results = fts_fts5.search("the a an")
        assert results == []

    def test_search_memory_stopwords_only(self, fts_memory):
        """Query de solo stopwords en memoria debe retornar []."""
        fts_memory.index("d1", "contenido importante", {})
        results = fts_memory.search("the a an de la")
        assert results == []

    def test_snippet_with_short_query_terms(self):
        """Términos de 1-2 chars no deben buscarse."""
        text = "es un texto de prueba"
        snippet = FTSSearch._make_snippet(text, "es un")
        # "es" y "un" tienen <= 2 chars, no se buscan
        assert "**es**" not in snippet

    def test_fts_search_empty_after_stopword_filter(self, fts_memory):
        """Si tras filtrar stopwords no quedan términos, retornar []."""
        results = fts_memory._search_memory("the a", top_k=10, domain_filter=None)
        assert results == []

    def test_fts_alias_exists(self):
        """FTSSearchEngine debe ser alias de FTSSearch."""
        from harness.memory_rag.fts_search import FTSSearchEngine
        assert FTSSearchEngine is FTSSearch
