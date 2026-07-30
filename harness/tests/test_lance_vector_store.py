# pragma: allowlist secret
"""Tests exhaustivos para LanceVectorStore con branch coverage >80%.

Los tests se han organizado en varios archivos para mejor mantenibilidad:

  - test_lance_vector_store_init.py   â†’ TestInitAndStorage
  - test_lance_vector_store_crud.py   â†’ TestCollectionManagement,
                                        TestInsert, TestUpdate,
                                        TestClearEdgeCases
  - test_lance_vector_store_search.py â†’ TestSearch, TestHybridSearch,
                                        TestStats, TestHybridSearchLanceDB

Estrategia general:
  - Modo memoria (allow_fallback=True): se parcha _try_import_lancedb para que
    retorne None. Cubre ~40% del cÃ³digo (fallback in-memory).
  - Modo LanceDB mockeado: se parcha _try_import_lancedb, os.makedirs y
    lancedb.connect. Cubre el resto (conexiÃ³n real, ensure_collections, etc.).
  - Cada metodo pÃºblico (insert, search, update, delete, etc.) se prueba en
    ambos modos cuando aplica, incluyendo edge cases y errores.
"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from harness.memory_rag.lance_schemas import DEFAULT_COLLECTIONS
from harness.memory_rag.lance_vector_store import (
    COLLECTION_PROCEDURAL_SKILLS,
    COLLECTION_PROMPT_EVOLUTION_LOG,
    COLLECTION_SCHEDULER_LOG,
    CollectionNotFoundError,
    LanceVectorStore,
    VectorStoreError,
)
from harness.memory_rag.memory_config import MemoryConfig

# ===========================================================================
# TESTS â€” Errores y hardening
# ===========================================================================


class TestErrorHandling:
    """Edge cases de error handling en ambos modos."""

    def test_init_import_error_message(self):
        """El mensaje de ImportError es claro y descriptivo."""
        with patch.object(LanceVectorStore, "_try_import_lancedb", return_value=None):  # noqa: SIM117
            with pytest.raises(ImportError) as excinfo:
                LanceVectorStore(db_path="/tmp/x", allow_fallback=False)
        msg = str(excinfo.value)
        assert "LanceDB no esta instalado" in msg
        assert "pip install lancedb" in msg

    def test_init_runtime_error_message(self, mock_lancedb):
        """El mensaje de RuntimeError incluye la ruta y el error original."""
        mock_lancedb["lancedb_module"].connect.side_effect = PermissionError(
            "access denied"
        )
        patches = [
            patch.object(
                LanceVectorStore,
                "_try_import_lancedb",
                return_value=mock_lancedb["lancedb_module"],
            ),
            patch("harness.memory_rag.lance_vector_store.Path.mkdir"),
        ]
        with patches[0], patches[1], pytest.raises(RuntimeError) as excinfo:
            LanceVectorStore(db_path="/custom/path", allow_fallback=False)
        msg = str(excinfo.value)
        assert "/custom/path" in msg
        assert "access denied" in msg

    def test_insert_lancedb_open_fails_propagates(self, lancedb_store, mock_lancedb):
        """Si open_table falla en insert, la excepciÃ³n se propaga."""
        mock_lancedb["db_conn"].open_table.side_effect = RuntimeError(
            "table missing"
        )
        vec = np.ones((1, 384), dtype=np.float32)
        with pytest.raises(RuntimeError) as excinfo:
            lancedb_store.insert("missing_table", vec, [{"k": "v"}])
        assert "table missing" in str(excinfo.value)

    def test_delete_collection_nonexistent_lancedb(self, lancedb_store, mock_lancedb):
        """delete_collection de tabla que no existe en LanceDB propaga error."""
        mock_lancedb["db_conn"].drop_table.side_effect = RuntimeError("not found")
        with pytest.raises(VectorStoreError):
            lancedb_store.delete_collection("ghost")

    def test_from_config_default(self):
        """from_config sin argumentos usa get_memory_config()."""
        cfg = MemoryConfig(
            lancedb_path="/tmp/test_from_config",
            allow_fallback=True,
        )
        with patch.object(
            LanceVectorStore, "_try_import_lancedb", return_value=None
        ), patch(
            "harness.memory_rag.lance_vector_store.get_memory_config",
            return_value=cfg,
        ):
            store = LanceVectorStore.from_config()
        assert store is not None
        assert store._allow_fallback is True

    def test_from_config_with_config(self):
        """from_config con MemoryConfig explÃ­cito."""
        cfg = MemoryConfig(
            lancedb_path="/custom/lancedb",
            allow_fallback=True,
        )
        with patch.object(LanceVectorStore, "_try_import_lancedb", return_value=None):
            store = LanceVectorStore.from_config(config=cfg)
        assert store.db_path == "/custom/lancedb"
        assert store._allow_fallback is True

    @pytest.mark.parametrize(
        "method_name,args,kwargs",
        [
            ("search", ("ghost", np.zeros(384, dtype=np.float32)), {}),
            ("get_collection_stats", ("ghost",), {}),
            (
                "update_records",
                ("ghost",),
                {"filters": {"x": 1}, "updates": {"y": 2}},
            ),
        ],
    )
    def test_all_methods_collection_not_found_memory(
        self, mem_store, method_name, args, kwargs
    ):
        """Todos los mÃ©todos lanzan CollectionNotFoundError en memoria."""
        method = getattr(mem_store, method_name)
        with pytest.raises(CollectionNotFoundError):
            method(*args, **kwargs)


# ===========================================================================
# TESTS â€” Constantes de colecciÃ³n
# ===========================================================================


class TestCollectionConstants:
    """Verifica que las constantes exportadas sean correctas."""

    def test_collection_constants(self):
        """Las constantes COLLECTION_* matchean claves en DEFAULT_COLLECTIONS."""
        assert COLLECTION_PROCEDURAL_SKILLS in DEFAULT_COLLECTIONS
        assert COLLECTION_PROMPT_EVOLUTION_LOG in DEFAULT_COLLECTIONS
        assert COLLECTION_SCHEDULER_LOG in DEFAULT_COLLECTIONS
        assert COLLECTION_PROCEDURAL_SKILLS == "procedural_skills"
        assert COLLECTION_PROMPT_EVOLUTION_LOG == "prompt_evolution_log"
        assert COLLECTION_SCHEDULER_LOG == "scheduler_log"
