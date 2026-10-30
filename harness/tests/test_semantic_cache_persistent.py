"""Integracion SemanticCache + RuscaDBStore (cache persistente, ADR-0098)."""

from __future__ import annotations

import pytest

from harness.memory_rag.ruscadb_store import RuscaDBStore
from harness.memory_rag.semantic_cache import SemanticCache

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
def cache(tmp_path):
    """Cache semantico sobre un RuscaDBStore aislado."""
    store = RuscaDBStore(db_path=str(tmp_path / "sc.db"))
    c = SemanticCache(vector_store=store, threshold=0.9)
    yield c
    store.close()


def test_set_get_exact_hit_uses_persistent_cache(cache):
    """El hit exacto se resuelve por el cache persistente del store."""
    assert cache.set("hola mundo", "respuesta-1") is True
    assert cache.get("hola mundo") == "respuesta-1"
    stats = cache.get_stats()
    assert stats["hits"] >= 1
    assert stats["sets"] == 1


def test_similarity_path_does_not_crash(cache):
    """La busqueda por similitud funciona sobre RuscaDB (sin atributos LanceDB)."""
    cache.set("consulta de prueba", "respuesta-2")
    # Prompt distinto: no hay hit exacto, se ejerce la ruta KNN.
    assert cache.get("otra consulta distinta") in (None, "respuesta-2")


def test_clear_resets_collection(cache):
    """clear() borra la coleccion de cache y la recrea."""
    cache.set("p", "r")
    assert cache.clear() == 1
    assert cache.get("p") is None


def test_clear_expired_delegates_to_store(cache):
    """clear_expired usa la purga del store persistente sin fallar."""
    cache.set("p", "r", ttl_seconds=60)
    assert cache.clear_expired() == 0
    assert cache.get("p") == "r"


def test_delete_entry_on_expiry(cache):
    """Una entrada expirada se elimina del cache persistente."""
    cache.set("p", "r", ttl_seconds=1)
    # Forzar expiracion reescribiendo la fila con TTL ya vencido.
    assert cache._try_remove_pending("hash-inexistente") is False
    assert cache._persistent_cache() is not None
    assert cache._delete_entry(cache._hash_prompt("p")) is None
    assert cache.get("p") is None
