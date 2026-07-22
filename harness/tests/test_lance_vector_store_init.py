# pragma: allowlist secret
"""Tests de inicialización para LanceVectorStore.

Extraído de test_lance_vector_store.py — pruebas de __init__, _init_storage(),
_try_import_lancedb y _ensure_lancedb_collections.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from harness.memory_rag.lance_schemas import DEFAULT_COLLECTIONS
from harness.memory_rag.lance_vector_store import LanceVectorStore
from harness.memory_rag.memory_config import MemoryConfig

# ===========================================================================
# TESTS — Inicialización y storage
# ===========================================================================


class TestInitAndStorage:
    """Prueba todos los caminos de __init__ y _init_storage()."""

    def test_init_memory_fallback(self):
        """__init__ con allow_fallback=True y LanceDB ausente crea store en memoria."""
        with patch.object(LanceVectorStore, "_try_import_lancedb", return_value=None):
            store = LanceVectorStore(db_path="/tmp/mem", allow_fallback=True)
        assert store._lancedb_available is False
        assert store._db is None
        assert len(store._mem_collections) == len(DEFAULT_COLLECTIONS)
        assert store._allow_fallback is True

    def test_init_no_fallback_raises_importerror(self):
        """__init__ con allow_fallback=False y LanceDB ausente lanza ImportError."""
        with patch.object(LanceVectorStore, "_try_import_lancedb", return_value=None):
            with pytest.raises(ImportError) as excinfo:
                LanceVectorStore(db_path="/tmp/mem", allow_fallback=False)
        assert "LanceDB no esta instalado" in str(excinfo.value)

    def test_init_lancedb_connect_success(self, mock_lancedb):
        """__init__ con LanceDB disponible conecta exitosamente."""
        patches = [
            patch.object(
                LanceVectorStore, "_try_import_lancedb",
                return_value=mock_lancedb["lancedb_module"],
            ),
            patch("harness.memory_rag.lance_vector_store.os.makedirs"),
        ]
        with patches[0], patches[1]:
            store = LanceVectorStore(db_path="/fake/path", allow_fallback=False)
        assert store._lancedb_available is True
        assert store._db is mock_lancedb["db_conn"]
        # Debió llamar a ensure_collections
        mock_lancedb["db_conn"].list_tables.assert_called_once()
        mock_lancedb["db_conn"].create_table.assert_not_called()  # ya existen

    def test_init_lancedb_connect_fails_no_fallback_raises(self, mock_lancedb):
        """Conexión a LanceDB falla sin fallback → RuntimeError."""
        mock_lancedb["lancedb_module"].connect.side_effect = OSError("permission denied")
        patches = [
            patch.object(
                LanceVectorStore, "_try_import_lancedb",
                return_value=mock_lancedb["lancedb_module"],
            ),
            patch("harness.memory_rag.lance_vector_store.os.makedirs"),
        ]
        with patches[0], patches[1]:
            with pytest.raises(RuntimeError) as excinfo:
                LanceVectorStore(db_path="/fake/path", allow_fallback=False)
        assert "LanceDB no pudo conectarse" in str(excinfo.value)

    def test_init_lancedb_connect_fails_with_fallback(self, mock_lancedb):
        """Conexión a LanceDB falla con allow_fallback=True → modo memoria."""
        mock_lancedb["lancedb_module"].connect.side_effect = OSError("permission denied")
        patches = [
            patch.object(
                LanceVectorStore, "_try_import_lancedb",
                return_value=mock_lancedb["lancedb_module"],
            ),
            patch("harness.memory_rag.lance_vector_store.os.makedirs"),
        ]
        with patches[0], patches[1]:
            store = LanceVectorStore(db_path="/fake/path", allow_fallback=True)
        assert store._lancedb_available is False
        assert store._db is None
        assert len(store._mem_collections) == len(DEFAULT_COLLECTIONS)

    def test_init_with_config_object(self):
        """__init__ con objeto MemoryConfig usa db_path y allow_fallback del config."""
        cfg = MemoryConfig(
            lancedb_path="/cfg/path",
            allow_fallback=True,
            backend="lancedb",  # type: ignore[arg-type]
        )
        with patch.object(LanceVectorStore, "_try_import_lancedb", return_value=None):
            store = LanceVectorStore(config=cfg)
        # db_path debe venir del config porque no se pasó explícito
        assert store.db_path == "/cfg/path"
        assert store._allow_fallback is True

    def test_init_config_overrides_explicit(self):
        """__init__ con config + db_path explícito prioriza el explícito."""
        cfg = MemoryConfig(
            lancedb_path="/cfg/path",
            allow_fallback=False,
        )
        with patch.object(LanceVectorStore, "_try_import_lancedb", return_value=None):
            store = LanceVectorStore(db_path="/explicit/path", allow_fallback=True, config=cfg)
        assert store.db_path == "/explicit/path"
        # allow_fallback explícito True prevalece sobre config False
        assert store._allow_fallback is True

    def test_init_config_allow_fallback_from_config(self):
        """Si no se pasa allow_fallback explícito, se usa el del config."""
        cfg = MemoryConfig(
            lancedb_path="/cfg/path",
            allow_fallback=True,
        )
        with patch.object(LanceVectorStore, "_try_import_lancedb", return_value=None):
            store = LanceVectorStore(config=cfg)
        assert store._allow_fallback is True

    def test_init_no_config_uses_default_root(self):
        """Sin config ni db_path, se usa LANCEDB_ROOT."""
        with patch.object(LanceVectorStore, "_try_import_lancedb", return_value=None):
            store = LanceVectorStore(allow_fallback=True)
        # LANCEDB_ROOT incluye "db/lancedb"
        assert "db" in store.db_path
        assert "lancedb" in store.db_path

    def test_try_import_lancedb_success(self):
        """_try_import_lancedb retorna el módulo cuando está instalado."""
        # El test se ejecuta en un entorno donde lancedb puede no estar
        # instalado; usamos patch para simular
        fake_lancedb = MagicMock()
        fake_lancedb.connect.return_value = None
        with patch("builtins.__import__", return_value=fake_lancedb):
            result = LanceVectorStore._try_import_lancedb()
        assert result is fake_lancedb

    def test_try_import_lancedb_failure(self):
        """_try_import_lancedb retorna None cuando lancedb no está instalado."""
        with patch("builtins.__import__", side_effect=ImportError):
            result = LanceVectorStore._try_import_lancedb()
        assert result is None

    def test_ensure_lancedb_collections_guard(self, mem_store):
        """_ensure_lancedb_collections no hace nada en modo memoria."""
        # En modo memoria, _lancedb_available es False → early return
        mem_store._ensure_lancedb_collections()
        # No debe explotar; no hay assert adicional necesario

    def test_ensure_lancedb_collections_creates_missing(self, mock_lancedb):
        """_ensure_lancedb_collections crea tablas que no existen."""
        # Simular que solo existen algunas tablas
        existing_tables = {"rag_chunks", "tasks_board"}
        mock_lancedb["table_list"].tables = existing_tables

        patches = [
            patch.object(
                LanceVectorStore, "_try_import_lancedb",
                return_value=mock_lancedb["lancedb_module"],
            ),
            patch("harness.memory_rag.lance_vector_store.os.makedirs"),
        ]
        with patches[0], patches[1]:
            store = LanceVectorStore(db_path="/fake/path", allow_fallback=False)

        # Debió crear las tablas faltantes
        total = len(DEFAULT_COLLECTIONS)
        missing = total - len(existing_tables)
        assert mock_lancedb["db_conn"].create_table.call_count == missing
        # La tabla mockeada open_table debe haberse llamado para delete("id = 'init'")
        assert mock_lancedb["db_conn"].open_table.call_count >= missing

    def test_ensure_lancedb_collections_create_fails_logs(self, mock_lancedb, caplog):
        """_ensure_lancedb_collections loggea warning si create_table falla."""
        mock_lancedb["table_list"].tables = set()
        mock_lancedb["db_conn"].create_table.side_effect = RuntimeError("disk full")

        patches = [
            patch.object(
                LanceVectorStore, "_try_import_lancedb",
                return_value=mock_lancedb["lancedb_module"],
            ),
            patch("harness.memory_rag.lance_vector_store.os.makedirs"),
        ]
        with caplog.at_level(logging.WARNING), patches[0], patches[1]:
            LanceVectorStore(db_path="/fake/path", allow_fallback=False)

        assert any("Could not create table" in rec.message for rec in caplog.records), (
            "Debería loggear warning al fallar create_table"
        )
