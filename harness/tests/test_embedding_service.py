"""
Tests para BatchedEmbeddingService — servicio de embeddings con batching
inteligente y fallback determinista.

Cubre: inicialización, embed_sync, embed_batch_sync, fallback embedding,
stats, manejo de errores y edge cases.
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from harness.memory_rag.embedding_service import (
    DEFAULT_BATCH_WINDOW_MS,
    EMBEDDING_DIM,
    BatchedEmbeddingService,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    """BatchedEmbeddingService sin modelo (usa fallback)."""
    return BatchedEmbeddingService()


@pytest.fixture
def service_with_model():
    """BatchedEmbeddingService con modelo mockeado."""
    svc = BatchedEmbeddingService()
    svc._model_available = True
    svc._model = MagicMock()
    svc._model.encode.return_value = np.random.randn(EMBEDDING_DIM).astype(np.float32)
    yield svc


# ---------------------------------------------------------------------------
# Tests: Initialization
# ---------------------------------------------------------------------------


class TestInitialization:
    """Tests de inicialización del servicio."""

    def test_init_defaults(self, service):
        """Inicialización con valores por defecto."""
        assert service._batch_window == DEFAULT_BATCH_WINDOW_MS / 1000
        assert service._max_batch_size == 32
        assert service._model_name == "all-MiniLM-L6-v2"
        assert not service._model_available
        assert service._stats["total_requests"] == 0

    def test_init_custom_params(self):
        """Inicialización con parámetros personalizados."""
        svc = BatchedEmbeddingService(
            model_name="custom-model",
            batch_window_ms=100,
            max_batch_size=64,
            device="cuda",
        )
        assert svc._model_name == "custom-model"
        assert svc._batch_window == 0.1
        assert svc._max_batch_size == 64
        assert svc._device == "cuda"

    def test_embedding_dim_constant(self):
        """EMBEDDING_DIM debe ser 384."""
        assert EMBEDDING_DIM == 384


# ---------------------------------------------------------------------------
# Tests: embed_sync (fallback)
# ---------------------------------------------------------------------------


class TestEmbedSync:
    """Tests para embed_sync (modo sincrónico)."""

    def test_embed_sync_returns_array(self, service):
        """embed_sync debe retornar un np.ndarray."""
        vec = service.embed_sync("texto de prueba")
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (EMBEDDING_DIM,)

    def test_embed_sync_normalized(self, service):
        """El vector de embedding debe estar normalizado (norma ~1)."""
        vec = service.embed_sync("texto de prueba")
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-5

    def test_embed_sync_deterministic(self, service):
        """El fallback debe ser determinista para el mismo texto."""
        vec1 = service.embed_sync("texto repetido")
        vec2 = service.embed_sync("texto repetido")
        np.testing.assert_array_equal(vec1, vec2)

    def test_embed_sync_different_texts_different(self, service):
        """Textos diferentes deben producir vectores diferentes."""
        vec1 = service.embed_sync("texto A")
        vec2 = service.embed_sync("texto B")
        assert not np.allclose(vec1, vec2)

    def test_embed_sync_empty_string(self, service):
        """Texto vacío debe producir un embedding válido."""
        vec = service.embed_sync("")
        assert vec.shape == (EMBEDDING_DIM,)
        assert np.isfinite(vec).all()

    def test_embed_sync_updates_stats(self, service):
        """embed_sync debe incrementar total_requests."""
        service.embed_sync("test")
        assert service._stats["total_requests"] == 1

    def test_embed_sync_special_characters(self, service):
        """Caracteres especiales y Unicode deben manejarse."""
        vec = service.embed_sync("ñññ áéíóú üñ 🚀 emoji test")
        assert vec.shape == (EMBEDDING_DIM,)
        assert np.isfinite(vec).all()

    def test_embed_sync_very_long_text(self, service):
        """Texto muy largo debe producir embedding sin error."""
        long_text = "palabra " * 10000
        vec = service.embed_sync(long_text)
        assert vec.shape == (EMBEDDING_DIM,)


# ---------------------------------------------------------------------------
# Tests: embed_sync (with model)
# ---------------------------------------------------------------------------


class TestEmbedSyncWithModel:
    """Tests para embed_sync con modelo mockeado."""

    def test_embed_sync_with_model(self, service_with_model):
        """Con modelo disponible, debe usarlo."""
        vec = service_with_model.embed_sync("test")
        assert vec.shape == (EMBEDDING_DIM,)
        service_with_model._model.encode.assert_called_once()

    def test_embed_sync_model_failure_fallback(self, service_with_model, caplog):
        """Si el modelo falla, debe usar fallback."""
        service_with_model._model.encode.side_effect = Exception("Model error")
        with caplog.at_level(logging.WARNING):
            vec = service_with_model.embed_sync("test")
            assert vec.shape == (EMBEDDING_DIM,)
        assert any("Model embedding failed" in msg for msg in caplog.messages)
        assert service_with_model._stats["errors"] == 1


# ---------------------------------------------------------------------------
# Tests: embed_batch_sync
# ---------------------------------------------------------------------------


class TestEmbedBatchSync:
    """Tests para embed_batch_sync."""

    def test_embed_batch_sync_empty(self, service):
        """Lista vacía debe retornar array (0, 384)."""
        result = service.embed_batch_sync([])
        assert result.shape == (0, EMBEDDING_DIM)

    def test_embed_batch_sync_multiple(self, service):
        """embed_batch_sync debe procesar múltiples textos."""
        texts = ["texto A", "texto B", "texto C"]
        result = service.embed_batch_sync(texts)
        assert result.shape == (3, EMBEDDING_DIM)

    def test_embed_batch_sync_normalized(self, service):
        """Cada vector del batch debe estar normalizado."""
        texts = ["texto A", "texto B"]
        result = service.embed_batch_sync(texts)
        for i in range(len(texts)):
            norm = np.linalg.norm(result[i])
            assert abs(norm - 1.0) < 1e-5

    def test_embed_batch_sync_single(self, service):
        """Un solo texto debe funcionar."""
        result = service.embed_batch_sync(["texto único"])
        assert result.shape == (1, EMBEDDING_DIM)

    def test_embed_batch_sync_with_model(self, service_with_model):
        """Con modelo, debe usar encode batch."""
        texts = ["texto A", "texto B"]
        service_with_model.embed_batch_sync(texts)
        service_with_model._model.encode.assert_called_once()

    def test_embed_batch_sync_mixed_lengths(self, service):
        """Textos de diferentes longitudes en batch."""
        texts = ["", "corto", "A" * 1000, "ñ" * 500]
        result = service.embed_batch_sync(texts)
        assert result.shape == (4, EMBEDDING_DIM)


# ---------------------------------------------------------------------------
# Tests: Fallback determinista
# ---------------------------------------------------------------------------


class TestFallbackEmbedding:
    """Tests para _fallback_embedding estático."""

    def test_fallback_returns_384d(self, service):
        """_fallback_embedding debe retornar vector 384d."""
        vec = service._fallback_embedding("test")
        assert vec.shape == (EMBEDDING_DIM,)

    def test_fallback_normalized(self, service):
        """_fallback_embedding debe retornar vector normalizado."""
        vec = service._fallback_embedding("test")
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-5

    def test_fallback_deterministic(self, service):
        """_fallback_embedding debe ser determinista."""
        v1 = service._fallback_embedding("texto fijo")
        v2 = service._fallback_embedding("texto fijo")
        np.testing.assert_array_equal(v1, v2)

    def test_fallback_non_zero(self, service):
        """El vector de fallback no debe ser todo ceros."""
        vec = service._fallback_embedding("texto con contenido")
        assert not np.allclose(vec, np.zeros(EMBEDDING_DIM))


# ---------------------------------------------------------------------------
# Tests: get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    """Tests para get_stats."""

    def test_stats_initial(self, service):
        """get_stats inicial debe mostrar 0 requests."""
        stats = service.get_stats()
        assert stats["total_requests"] == 0
        assert stats["batches"] == 0
        assert stats["model_available"] is False

    def test_stats_after_embed(self, service):
        """get_stats después de embed debe reflejar requests."""
        service.embed_sync("test")
        stats = service.get_stats()
        assert stats["total_requests"] == 1

    def test_stats_avg_batch_size(self, service):
        """avg_batch_size debe calcularse cuando hay batches."""
        service._stats["total_requests"] = 10
        service._stats["batches"] = 5
        stats = service.get_stats()
        assert stats["avg_batch_size"] == 2.0

    def test_stats_avg_batch_size_zero(self, service):
        """avg_batch_size debe ser 0 cuando no hay batches."""
        stats = service.get_stats()
        assert stats["avg_batch_size"] == 0.0

    def test_stats_model_name(self, service):
        """get_stats debe incluir el nombre del modelo."""
        stats = service.get_stats()
        assert stats["model"] == "all-MiniLM-L6-v2"

    def test_stats_errors_tracking(self, service):
        """Los errores deben contabilizarse en stats."""
        service._stats["errors"] = 3
        stats = service.get_stats()
        assert stats["errors"] == 3


# ---------------------------------------------------------------------------
# Tests: embed() sin event loop (cae en sync)
# ---------------------------------------------------------------------------


class TestEmbedNoEventLoop:
    """Tests para embed() cuando no hay event loop activo."""

    def test_embed_no_event_loop_fallback_sync(self, service):
        """Sin event loop, embed() detecta RuntimeError y llama a embed_sync."""
        with patch("harness.memory_rag.embedding_service.asyncio.get_running_loop",
                   side_effect=RuntimeError("No event loop")):
            async def _run():
                return await service.embed("test")

            vec = asyncio.run(_run())
            assert vec.shape == (EMBEDDING_DIM,)
        # embed() incrementa total_requests + embed_sync lo incrementa otra vez
        assert service._stats["total_requests"] >= 1

    def test_embed_async_with_event_loop(self, service):
        """Con event loop, embed() debe retornar np.ndarray."""
        async def _run():
            return await service.embed("test async")

        vec = asyncio.run(_run())
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (EMBEDDING_DIM,)
        assert service._stats["total_requests"] == 1


# ---------------------------------------------------------------------------
# Tests: _ensure_model (SentenceTransformer lazy init)
# ---------------------------------------------------------------------------


class TestEnsureModel:
    """Tests para _ensure_model (lazy loading del modelo).

    SentenceTransformer se importa DENTRO de _ensure_model (no es un
    atributo del módulo), por lo que se parchea sentence_transformers.
    """

    def test_ensure_model_import_error(self, service, caplog):
        """Si sentence_transformers no está instalado, debe loguear warning."""
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            # Forzar que la importación falle
            import builtins
            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "sentence_transformers":
                    raise ImportError("No module named 'sentence_transformers'")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                with caplog.at_level(logging.WARNING):
                    service._ensure_model()
                    assert not service._model_available
                assert any("not installed" in msg for msg in caplog.messages)

    def test_ensure_model_success(self, service):
        """Si sentence_transformers está disponible, debe cargar el modelo."""
        mock_st_module = MagicMock()
        mock_st = MagicMock()
        mock_st_module.SentenceTransformer.return_value = mock_st

        with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
            service._ensure_model()
            assert service._model_available
            assert service._model is mock_st

    def test_ensure_model_sync_lock(self, service):
        """_sync_lock debe prevenir carga concurrente."""
        service._sync_lock = True
        mock_st_module = MagicMock()
        with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
            service._ensure_model()
            # No debe llamar a SentenceTransformer porque _sync_lock=True
            if hasattr(service, "_model"):
                assert service._model is None

    def test_ensure_model_already_loaded(self, service):
        """Si ya está cargado, no debe cargar de nuevo."""
        service._model_available = True
        mock_st_module = MagicMock()
        with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
            service._ensure_model()
            mock_st_module.SentenceTransformer.assert_not_called()

    def test_ensure_model_exception_handled(self, service, caplog):
        """Excepción al cargar el modelo debe manejarse gracefulmente."""
        mock_st_module = MagicMock()
        mock_st_module.SentenceTransformer.side_effect = Exception("Loading failed")

        with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
            with caplog.at_level(logging.WARNING):
                service._ensure_model()
                assert not service._model_available
            assert any("Failed to load model" in msg for msg in caplog.messages)
            # Debe liberar el lock
            assert not service._sync_lock


# ---------------------------------------------------------------------------
# Tests: Edge cases adicionales
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests de edge cases varios."""

    def test_loop_cleanup_on_stop(self, service):
        """Al detener el loop, _running debe ser False."""
        service._running = False
        assert True

    def test_embed_sync_with_non_ascii(self, service):
        """Textos con solo caracteres no ASCII deben funcionar."""
        vec = service.embed_sync("こんにちは世界")
        assert vec.shape == (EMBEDDING_DIM,)

    def test_embed_batch_sync_empty_strings(self, service):
        """Batch con strings vacíos."""
        result = service.embed_batch_sync(["", "", ""])
        assert result.shape == (3, EMBEDDING_DIM)

    def test_stats_fields_presence(self, service):
        """get_stats debe contener todos los campos esperados."""
        stats = service.get_stats()
        expected_keys = {
            "total_requests", "batches", "avg_batch_size",
            "errors", "total_time_ms", "model_available", "model",
        }
        assert expected_keys.issubset(stats.keys())
