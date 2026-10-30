"""Tests de invalidacion por version y politica fail-closed del SemanticCache."""

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
def store(tmp_path):
    """Store RuscaDB aislado por test."""
    s = RuscaDBStore(db_path=str(tmp_path / "cache.db"))
    yield s
    s.close()


def test_version_bump_invalidates_entries(store):
    """Cambiar dataset_version deja de servir las respuestas anteriores."""
    v1 = SemanticCache(vector_store=store, dataset_version="ds-1")
    assert v1.set("pregunta", "respuesta-v1") is True
    assert v1.get("pregunta") == "respuesta-v1"

    v2 = SemanticCache(vector_store=store, dataset_version="ds-2")
    assert v2.get("pregunta") is None
    # El invalidador purga las entradas de la version anterior.
    assert v2.invalidate_version() == 1
    assert v2.get("pregunta") is None


def test_invalidate_version_explicit_target(store):
    """invalidate_version(version) conserva las entradas de esa version."""
    v1 = SemanticCache(vector_store=store, dataset_version="ds-1")
    v1.set("p", "r1")
    assert v1.invalidate_version("ds-1") == 0
    assert v1.get("p") == "r1"


def test_stats_expose_version_and_policy(store):
    """get_stats publica dataset_version/fail_closed para telemetria."""
    cache = SemanticCache(
        vector_store=store, dataset_version="ds-9", fail_closed=True
    )
    stats = cache.get_stats()
    assert stats["dataset_version"] == "ds-9"
    assert stats["fail_closed"] is True


def test_fail_closed_rejects_unverified_hits(store):
    """Con fail_closed, una entrada sin verified=True se trata como miss."""
    cache = SemanticCache(vector_store=store, fail_closed=True)
    cache.set("p", "sin-verificar")
    assert cache.get("p") is None

    verified = SemanticCache(vector_store=store, fail_closed=True)
    verified.set("q", "verificado", metadata={"verified": True})
    assert verified.get("q") == "verificado"


def test_fail_open_default_serves_unverified(store):
    """Por defecto (fail_closed=False) una entrada normal si se sirve."""
    cache = SemanticCache(vector_store=store)
    cache.set("p", "r")
    assert cache.get("p") == "r"
