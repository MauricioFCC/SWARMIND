"""
Tests para cognition_sync — CognitionSync, CognitionLesson.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from harness.evolve_loop.cognition_sync import CognitionLesson, CognitionSync
from harness.tests.mock_vector_store import MockVectorStore

# ---------------------------------------------------------------------------
# Fixtures locales
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_store():
    """MockVectorStore con coleccion cognition pre-creada."""
    store = MockVectorStore()
    store.create_collection("asi_cognition_store")
    return store


@pytest.fixture
def sync(mock_store):
    """CognitionSync con MockVectorStore y embedding por defecto."""
    return CognitionSync(vector_store=mock_store)


# ===================================================================
# CognitionLesson
# ===================================================================


class TestCognitionLesson:
    """Tests para el dataclass CognitionLesson."""

    def test_to_dict(self):
        """Test to_dict exporta todos los campos."""
        lesson = CognitionLesson(
            id="abc-123",
            title="Test Lesson",
            content="Some content",
            domain="testing",
            tags=["tag1", "tag2"],
            metrics={"score": 0.9},
            created_at="2026-07-27T00:00:00Z",
            access_count=5,
            last_accessed="2026-07-28T00:00:00Z",
        )
        d = lesson.to_dict()
        assert d["id"] == "abc-123"
        assert d["title"] == "Test Lesson"
        assert d["domain"] == "testing"
        assert d["tags"] == ["tag1", "tag2"]
        assert d["metrics"]["score"] == 0.9
        assert d["access_count"] == 5

    def test_from_dict(self):
        """Test from_dict reconstruye desde dict."""
        data = {
            "id": "xyz-789",
            "title": "Reconstructed",
            "content": "Reconstructed content",
            "domain": "ml",
            "tags": ["ml", "test"],
            "metrics": {"overall": 0.95},
            "created_at": "2026-07-26T00:00:00Z",
            "access_count": 3,
            "last_accessed": "2026-07-27T00:00:00Z",
        }
        lesson = CognitionLesson.from_dict(data)
        assert lesson.id == "xyz-789"
        assert lesson.title == "Reconstructed"
        assert lesson.domain == "ml"
        assert lesson.access_count == 3

    def test_from_dict_empty(self):
        """Test from_dict con dict vacio usa defaults."""
        lesson = CognitionLesson.from_dict({})
        assert lesson.id == ""
        assert lesson.title == ""
        assert lesson.tags == []
        assert lesson.access_count == 0


# ===================================================================
# CognitionSync
# ===================================================================


class TestCognitionSyncInit:
    """Tests de inicializacion de CognitionSync."""

    def test_init_defaults(self):
        """Test init sin argumentos crea dependencias por defecto."""
        with patch("harness.evolve_loop.cognition_sync.LanceVectorStore") as mock_cls:
            cs = CognitionSync()
            mock_cls.assert_called_once()
            assert cs.store is not None
            assert cs._embedding_fn is not None

    def test_init_with_store(self, mock_store):
        """Test init con vector_store inyectado."""
        cs = CognitionSync(vector_store=mock_store)
        assert cs.store is mock_store

    def test_init_with_custom_embedding(self, mock_store):
        """Test init con embedding_fn personalizada."""
        fn = lambda x: np.zeros(384, dtype=np.float32)
        cs = CognitionSync(vector_store=mock_store, embedding_fn=fn)
        assert cs._embedding_fn is fn


class TestCognitionSyncAddLesson:
    """Tests para add_lesson."""

    def test_add_lesson_returns_lesson(self, sync):
        """Test add_lesson retorna CognitionLesson con id generado."""
        lesson = sync.add_lesson(
            title="Test Title",
            content="Test content body",
            domain="testing",
        )
        assert isinstance(lesson, CognitionLesson)
        assert lesson.id != ""
        assert lesson.title == "Test Title"
        assert lesson.domain == "testing"

    def test_add_lesson_persists_to_store(self, sync, mock_store):
        """Test add_lesson inserta en el vector store."""
        lesson = sync.add_lesson(
            title="Persist Test",
            content="Some content",
            domain="persist",
            tags=["test"],
            metrics={"score": 1.0},
        )
        # Verificar que se inserto buscando por id
        found = sync.get_lesson_by_id(lesson.id)
        assert found is not None
        assert found.title == "Persist Test"
        assert found.tags == ["test"]

    def test_add_lesson_store_exception(self, sync, mock_store):
        """Test add_lesson no propaga excepcion del store."""
        mock_store.insert = MagicMock(side_effect=RuntimeError("insert failed"))
        lesson = sync.add_lesson(
            title="Fail",
            content="Should not crash",
            domain="error",
        )
        assert lesson is not None  # se retorna aunque falle insercion
        assert lesson.id != ""

    def test_add_lesson_with_tags_and_metrics(self, sync):
        """Test add_lesson con tags y metrics completos."""
        lesson = sync.add_lesson(
            title="Full Lesson",
            content="Complete content for testing purposes",
            domain="full-test",
            tags=["alpha", "beta", "gamma"],
            metrics={"complexity": 0.7, "relevance": 0.9},
        )
        assert lesson.tags == ["alpha", "beta", "gamma"]
        assert lesson.metrics["complexity"] == 0.7
        assert lesson.metrics["relevance"] == 0.9


class TestCognitionSyncSearch:
    """Tests para search_lessons."""

    def test_search_lessons_empty(self, sync):
        """Test search_lessons retorna lista vacia cuando no hay datos."""
        results = sync.search_lessons("anything")
        assert results == []

    def test_search_lessons_finds_data(self, sync, mock_store):
        """Test search_lessons recupera lecciones insertadas."""
        sync.add_lesson(title="Trading Tip", content="Buy low sell high", domain="trading")
        results = sync.search_lessons("trading", top_k=10)
        assert len(results) >= 1
        assert any(r.domain == "trading" for r in results)

    def test_search_lessons_store_exception(self, sync, mock_store):
        """Test search_lessons retorna [] ante excepcion del store."""
        mock_store.search = MagicMock(side_effect=RuntimeError("search failed"))
        results = sync.search_lessons("query")
        assert results == []

    def test_search_lessons_respects_top_k(self, sync, mock_store):
        """Test search_lessons respeta limite top_k."""
        np.zeros(384, dtype=np.float32)
        for i in range(5):
            sync.add_lesson(title=f"Lesson {i}", content=f"Content {i}", domain=f"domain{i}")
        results = sync.search_lessons("test", top_k=3)
        assert len(results) <= 3


class TestCognitionSyncGetById:
    """Tests para get_lesson_by_id."""

    def test_get_lesson_by_id_found(self, sync):
        """Test get_lesson_by_id retorna leccion existente."""
        lesson = sync.add_lesson(title="Find Me", content="Content", domain="find")
        found = sync.get_lesson_by_id(lesson.id)
        assert found is not None
        assert found.id == lesson.id
        assert found.title == "Find Me"

    def test_get_lesson_by_id_not_found(self, sync):
        """Test get_lesson_by_id retorna None para id inexistente."""
        found = sync.get_lesson_by_id("nonexistent-id-999")
        assert found is None

    def test_get_lesson_by_id_store_exception(self, sync, mock_store):
        """Test get_lesson_by_id retorna None ante excepcion."""
        mock_store.search = MagicMock(side_effect=RuntimeError("store error"))
        found = sync.get_lesson_by_id("any-id")
        assert found is None


class TestCognitionSyncGetByDomain:
    """Tests para get_lessons_by_domain."""

    def test_get_by_domain_empty(self, sync):
        """Test retorna [] cuando no hay lecciones del dominio."""
        results = sync.get_lessons_by_domain("unknown")
        assert results == []

    def test_get_by_domain_finds(self, sync):
        """Test retorna solo lecciones del dominio solicitado."""
        sync.add_lesson(title="Trading A", content="Content", domain="trading")
        sync.add_lesson(title="ML Model", content="Content", domain="ml")
        sync.add_lesson(title="Trading B", content="Content", domain="trading")
        results = sync.get_lessons_by_domain("trading")
        assert len(results) == 2
        assert all(r.domain == "trading" for r in results)


class TestCognitionSyncGetAllTags:
    """Tests para get_all_tags."""

    def test_get_all_tags_empty(self, sync):
        """Test retorna [] cuando no hay lecciones."""
        tags = sync.get_all_tags()
        assert tags == []

    def test_get_all_tags_unique(self, sync):
        """Test retorna tags unicos de todas las lecciones."""
        sync.add_lesson(title="A", content="C", domain="d1", tags=["tag1", "tag2"])
        sync.add_lesson(title="B", content="C", domain="d2", tags=["tag2", "tag3"])
        tags = sync.get_all_tags()
        assert "tag1" in tags
        assert "tag2" in tags
        assert "tag3" in tags
        assert len(tags) == 3  # sin duplicados


class TestCognitionSyncDelete:
    """Tests para delete_lesson."""

    def test_delete_lesson_returns_false(self, sync):
        """Test delete_lesson retorna False (placeholder no implementado)."""
        result = sync.delete_lesson("any-id")
        assert result is False


class TestCognitionSyncEmbedding:
    """Tests para _default_embedding."""

    def test_default_embedding_output_shape(self):
        """Test _default_embedding produce vector de dimension correcta."""
        vec = CognitionSync._default_embedding("test text")
        assert vec.shape == (384,)
        assert vec.dtype == np.float32

    def test_default_embedding_normalized(self):
        """Test _default_embedding produce vector normalizado."""
        vec = CognitionSync._default_embedding("some longer text for embedding test")
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-6

    def test_default_embedding_deterministic(self):
        """Test _default_embedding es determinista (mismo texto → mismo vector)."""
        v1 = CognitionSync._default_embedding("hello world")
        v2 = CognitionSync._default_embedding("hello world")
        assert np.allclose(v1, v2)
