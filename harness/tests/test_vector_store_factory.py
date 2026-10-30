"""Tests de la factory de vector stores y del contrato ``VectorStorePort``."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.domain.ports import TextSearchPort, VectorStorePort
from harness.memory_rag.lance_vector_store import LanceVectorStore
from harness.memory_rag.ruscadb_store import RuscaDBStore
from harness.memory_rag.vector_store_factory import get_vector_store

try:
    from harness.memory_rag.ruscadb import load_library

    load_library()
    _RUSCADB_AVAILABLE = True
except Exception:  # noqa: BLE001
    _RUSCADB_AVAILABLE = False


def test_default_backend_returns_ruscadb(tmp_path):
    """Sin backend explicito la factory devuelve el adaptador RuscaDB."""
    store = get_vector_store(db_path=str(tmp_path / "t.db"))
    try:
        assert isinstance(store, RuscaDBStore)
        assert isinstance(store, VectorStorePort)
        assert isinstance(store, TextSearchPort)
    finally:
        store.close()


def test_explicit_lancedb_backend(tmp_path):
    """backend='lancedb' construye LanceVectorStore (fallback in-memory)."""
    store = get_vector_store(
        backend="lancedb",
        db_path=str(tmp_path / "lance"),
        allow_fallback=True,
    )
    try:
        assert type(store) is LanceVectorStore
        assert isinstance(store, VectorStorePort)
    finally:
        store.close()


def test_memory_backend_forces_fallback(tmp_path):
    """backend='memory' activa siempre el fallback in-memory."""
    store = get_vector_store(backend="memory", db_path=str(tmp_path / "mem"))
    try:
        assert store._allow_fallback is True
        assert isinstance(store, VectorStorePort)
    finally:
        store.close()


def test_env_var_selects_backend(tmp_path, monkeypatch):
    """VECTOR_BACKEND tiene precedencia sobre el default."""
    monkeypatch.setenv("VECTOR_BACKEND", "memory")
    store = get_vector_store(db_path=str(tmp_path / "envmem"))
    try:
        assert type(store) is LanceVectorStore
    finally:
        store.close()


def test_config_backend_is_respected(tmp_path, monkeypatch):
    """config.backend se usa cuando no hay argumento ni env var."""
    monkeypatch.delenv("VECTOR_BACKEND", raising=False)
    config = SimpleNamespace(backend="memory")
    store = get_vector_store(db_path=str(tmp_path / "cfg"), config=config)
    try:
        assert type(store) is LanceVectorStore
    finally:
        store.close()


def test_unsupported_backend_raises(tmp_path):
    """Un backend desconocido falla rapido con WHAT+WHY+WHERE."""
    with pytest.raises(ValueError) as excinfo:
        get_vector_store(backend="postgres", db_path=str(tmp_path / "x"))
    message = str(excinfo.value)
    assert "backend_invalido" in message
    assert "postgres" in message


def test_lance_store_redirects_to_ruscadb(tmp_path):
    """LanceVectorStore(backend='ruscadb') devuelve un RuscaDBStore real."""
    if not _RUSCADB_AVAILABLE:
        pytest.skip("RuscaDB C-ABI dll not available")
    store = LanceVectorStore(db_path=str(tmp_path / "redirect.db"))
    try:
        assert isinstance(store, RuscaDBStore)
        # Sin monkey-patching: el metodo pertenece a la clase del adaptador.
        assert "search" in type(store).__dict__
    finally:
        store.close()


def test_lance_store_explicit_backend_stays_lance(tmp_path):
    """backend explicito 'lancedb' no se redirige a RuscaDB."""
    store = LanceVectorStore(
        db_path=str(tmp_path / "lance2"), allow_fallback=True, backend="lancedb"
    )
    try:
        assert type(store) is LanceVectorStore
    finally:
        store.close()


def test_delete_and_close_are_part_of_port(tmp_path):
    """delete() y close() existen en ambos adaptadores (paridad de puerto)."""
    store = get_vector_store(
        backend="lancedb", db_path=str(tmp_path / "crud"), allow_fallback=True
    )
    try:
        import numpy as np

        ids = store.insert(
            "memory",
            np.ones((2, 8), dtype=np.float32),
            [{"k": 1}, {"k": 2}],
        )
        assert len(ids) == 2
        assert store.delete("memory", ids) == 2
        assert store.get_collection_stats("memory")["item_count"] == 0
    finally:
        store.close()
