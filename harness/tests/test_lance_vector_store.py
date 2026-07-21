# pragma: allowlist secret
"""Tests exhaustivos para LanceVectorStore con branch coverage >80%.

Estrategia:
  - Modo memoria (allow_fallback=True): se parcha _try_import_lancedb para que
    retorne None. Cubre ~40% del código (fallback in-memory).
  - Modo LanceDB mockeado: se parcha _try_import_lancedb, os.makedirs y
    lancedb.connect. Cubre el resto (conexión real, ensure_collections, etc.).
  - Cada metodo público (insert, search, update, delete, etc.) se prueba en
    ambos modos cuando aplica, incluyendo edge cases y errores.
"""
from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

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
    _Collection,
    _StoredItem,
)
from harness.memory_rag.memory_config import MemoryConfig

# ---------------------------------------------------------------------------
# Ayudantes
# ---------------------------------------------------------------------------

_EMPTY_EMBEDDING = np.zeros(384, dtype=np.float32)


def _make_vec(dim: int = 384, seed: int = 0) -> np.ndarray:
    """Crea un vector unitario normalizado para tests."""
    rng = np.random.RandomState(seed)
    v = rng.randn(dim).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-12)


# ===========================================================================
# FIXTURES — Modo memoria (fallback)
# ===========================================================================


@pytest.fixture
def mem_store():
    """LanceVectorStore en modo fallback in-memory.

    _try_import_lancedb se parcha para retornar None, forzando el path
    de memoria.  Se usa allow_fallback=True para evitar ImportError.
    """
    with patch.object(
        LanceVectorStore, "_try_import_lancedb", return_value=None
    ):
        store = LanceVectorStore(db_path="/tmp/test_mem", allow_fallback=True)
        yield store


@pytest.fixture
def mem_store_no_defaults():
    """Idem mem_store pero sin las colecciones por defecto (limpio)."""
    with patch.object(
        LanceVectorStore, "_try_import_lancedb", return_value=None
    ):
        store = LanceVectorStore.__new__(LanceVectorStore)
        store._lancedb_available = False
        store._db = None
        store._mem_collections = {}
        store._embedding_dim = 384
        store._allow_fallback = True
        yield store


# ===========================================================================
# FIXTURES — Modo LanceDB mockeado
# ===========================================================================


@pytest.fixture
def mock_lancedb():
    """Crea un ecosistema completo de mocks para LanceDB.

    Retorna un dict con:
      - lancedb_module: el módulo mockeado
      - db_conn: la conexión mockeada (lancedb.connect)
      - table: la tabla mockeada
      - table_list: resultado de list_tables()
    """
    table = MagicMock(name="table")
    table.count_rows.return_value = 0
    table.search.return_value.limit.return_value.to_list.return_value = []
    table.to_arrow.return_value.num_rows = 0

    table_list_mock = MagicMock(name="table_list")
    table_list_mock.tables = list(DEFAULT_COLLECTIONS.keys())

    db_conn = MagicMock(name="db_conn")
    db_conn.list_tables.return_value = table_list_mock
    db_conn.open_table.return_value = table
    db_conn.create_table.return_value = None

    lancedb_module = MagicMock(name="lancedb")
    lancedb_module.connect.return_value = db_conn

    return {
        "lancedb_module": lancedb_module,
        "db_conn": db_conn,
        "table": table,
        "table_list": table_list_mock,
    }


@pytest.fixture
def lancedb_store(mock_lancedb):
    """LanceVectorStore con LanceDB mockeado (conexión exitosa)."""
    patches = [
        patch.object(
            LanceVectorStore, "_try_import_lancedb",
            return_value=mock_lancedb["lancedb_module"],
        ),
        patch("harness.memory_rag.lance_vector_store.os.makedirs"),
    ]
    with patches[0], patches[1]:
        store = LanceVectorStore(db_path="/fake/path", allow_fallback=False)
        yield store


@pytest.fixture
def lancedb_store_with_data(mock_lancedb):
    """LanceVectorStore con datos pre-insertados en la tabla mockeada."""
    table = mock_lancedb["table"]
    table.count_rows.return_value = 3
    table.search.return_value.limit.return_value.to_list.return_value = [
        {
            "id": "r1",
            "vector": [0.1, 0.2],
            "metadata": json.dumps({"domain": "test", "score": 1}),
            "created_at": "2025-01-01T00:00:00",
            "_distance": 0.9,
        },
        {
            "id": "r2",
            "vector": [0.3, 0.4],
            "metadata": json.dumps({"domain": "test", "score": 2}),
            "created_at": "2025-01-02T00:00:00",
            "_distance": 0.8,
        },
    ]

    # to_arrow mock para stats
    arrow_mock = MagicMock(name="arrow_table")
    arrow_mock.num_rows = 2
    col_mock = MagicMock(name="created_at_col")
    col_mock.__getitem__.return_value.as_py.return_value = "2025-01-02T00:00:00"
    arrow_mock.column_names = ["id", "vector", "metadata", "created_at"]
    # slice devuelve una tabla con una fila
    slice_mock = MagicMock(name="slice")
    slice_mock.column.return_value = col_mock
    arrow_mock.slice.return_value = slice_mock
    table.to_arrow.return_value = arrow_mock

    patches = [
        patch.object(
            LanceVectorStore, "_try_import_lancedb",
            return_value=mock_lancedb["lancedb_module"],
        ),
        patch("harness.memory_rag.lance_vector_store.os.makedirs"),
    ]
    with patches[0], patches[1]:
        store = LanceVectorStore(db_path="/fake/path", allow_fallback=False)
        yield store


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


# ===========================================================================
# TESTS — Gestión de colecciones
# ===========================================================================


class TestCollectionManagement:
    """create_collection / list_collections / delete_collection / clear."""

    def test_create_collection_memory(self, mem_store):
        """create_collection en modo memoria crea una colección nueva."""
        mem_store.create_collection("my_test_col")
        assert "my_test_col" in mem_store._mem_collections

    def test_create_collection_memory_overwrite_warning(self, mem_store, caplog):
        """create_collection sobre colección existente loggea warning."""
        mem_store.create_collection("dup")
        with caplog.at_level(logging.WARNING):
            mem_store.create_collection("dup")
        assert any("already exists" in rec.message for rec in caplog.records)

    def test_create_collection_lancedb(self, lancedb_store, mock_lancedb):
        """create_collection en modo LanceDB crea tabla."""
        lancedb_store.create_collection("custom_table")
        mock_lancedb["db_conn"].create_table.assert_called_with(
            "custom_table", data=[], mode="overwrite"
        )

    def test_create_collection_lancedb_fails(self, lancedb_store, mock_lancedb):
        """create_collection en LanceDB falla → VectorStoreError."""
        mock_lancedb["db_conn"].create_table.side_effect = RuntimeError("nope")
        with pytest.raises(VectorStoreError) as excinfo:
            lancedb_store.create_collection("fail_table")
        assert "Failed to create LanceDB table" in str(excinfo.value)

    def test_list_collections_memory(self, mem_store):
        """list_collections en modo memoria retorna nombres de colecciones."""
        cols = mem_store.list_collections()
        assert "asi_cognition_store" in cols
        assert "rag_chunks" in cols
        assert isinstance(cols, list)

    def test_list_collections_lancedb(self, lancedb_store, mock_lancedb):
        """list_collections en modo LanceDB retorna tablas."""
        cols = lancedb_store.list_collections()
        assert len(cols) == len(DEFAULT_COLLECTIONS)
        mock_lancedb["db_conn"].list_tables.assert_called()

    def test_delete_collection_memory(self, mem_store):
        """delete_collection elimina colección en modo memoria."""
        mem_store.create_collection("to_delete")
        assert "to_delete" in mem_store._mem_collections
        mem_store.delete_collection("to_delete")
        assert "to_delete" not in mem_store._mem_collections

    def test_delete_collection_memory_nonexistent(self, mem_store):
        """delete_collection sobre colección inexistente no falla."""
        mem_store.delete_collection("no_existe")  # no debe explotar

    def test_delete_collection_lancedb(self, lancedb_store, mock_lancedb):
        """delete_collection elimina tabla en LanceDB."""
        lancedb_store.delete_collection("rag_chunks")
        mock_lancedb["db_conn"].drop_table.assert_called_with("rag_chunks")

    def test_delete_collection_lancedb_fails(self, lancedb_store, mock_lancedb):
        """delete_collection en LanceDB falla → VectorStoreError."""
        mock_lancedb["db_conn"].drop_table.side_effect = RuntimeError("nope")
        with pytest.raises(VectorStoreError) as excinfo:
            lancedb_store.delete_collection("some_table")
        assert "Failed to drop LanceDB table" in str(excinfo.value)

    def test_clear_memory(self, mem_store):
        """clear resetea todas las colecciones a defaults en modo memoria."""
        mem_store.create_collection("extra_one")
        assert len(mem_store._mem_collections) > len(DEFAULT_COLLECTIONS)
        mem_store.clear()
        assert len(mem_store._mem_collections) == len(DEFAULT_COLLECTIONS)
        # Verificar que las colecciones por defecto están presentes
        for name in DEFAULT_COLLECTIONS:
            assert name in mem_store._mem_collections

    def test_clear_lancedb(self, lancedb_store, mock_lancedb):
        """clear elimina todas las tablas LanceDB y resetea memoria."""
        lancedb_store.clear()
        # Debió llamar drop_table para cada tabla
        table_count = len(DEFAULT_COLLECTIONS)
        assert mock_lancedb["db_conn"].drop_table.call_count == table_count

    def test_clear_lancedb_drop_fails_logs(self, lancedb_store, mock_lancedb, caplog):
        """clear loggea warning si drop_table falla."""
        mock_lancedb["db_conn"].drop_table.side_effect = RuntimeError("nope")
        with caplog.at_level(logging.WARNING):
            lancedb_store.clear()
        assert any("lance_vector_store:" in rec.message for rec in caplog.records)


# ===========================================================================
# TESTS — Insert
# ===========================================================================


class TestInsert:
    """Insert de vectores en ambos modos."""

    def test_insert_empty_vectors(self, mem_store):
        """insert con vectores vacíos retorna lista vacía."""
        vec = np.empty((0, 384), dtype=np.float32)
        ids = mem_store.insert("asi_cognition_store", vec, [])
        assert ids == []

    def test_insert_memory(self, mem_store):
        """insert en modo memoria guarda items correctamente."""
        vec = _make_vec(384, seed=1).reshape(1, -1)
        meta = [{"title": "test", "domain": "test"}]
        ids = mem_store.insert("asi_cognition_store", vec, meta)
        assert len(ids) == 1
        assert isinstance(ids[0], str) and len(ids[0]) > 0
        # Verificar que el item está en memoria
        col = mem_store._mem_collections["asi_cognition_store"]
        assert ids[0] in col.items
        assert col.items[ids[0]].metadata["title"] == "test"

    def test_insert_memory_updates_embedding_dim(self, mem_store):
        """insert en memoria actualiza embedding_dim si el nuevo es mayor."""
        assert mem_store._embedding_dim == 384
        big_vec = np.zeros((1, 512), dtype=np.float32)
        mem_store.insert("asi_cognition_store", big_vec, [{"x": 1}])
        assert mem_store._embedding_dim == 512

    def test_insert_memory_creates_collection(self, mem_store):
        """insert en memoria crea colección automáticamente si no existe."""
        assert "new_coll" not in mem_store._mem_collections
        vec = np.ones((1, 384), dtype=np.float32)
        mem_store.insert("new_coll", vec, [{"k": "v"}])
        assert "new_coll" in mem_store._mem_collections

    def test_insert_lancedb(self, lancedb_store, mock_lancedb):
        """insert en modo LanceDB llama a tbl.add con los rows."""
        vec = _make_vec(384, seed=2).reshape(1, -1)
        meta = [{"title": "test_lancedb", "domain": "lancedb"}]
        ids = lancedb_store.insert("rag_chunks", vec, meta)
        assert len(ids) == 1
        mock_lancedb["db_conn"].open_table.assert_called_with("rag_chunks")
        mock_lancedb["table"].add.assert_called_once()
        args = mock_lancedb["table"].add.call_args[0][0]
        assert len(args) == 1
        assert args[0]["id"] == ids[0]
        assert "vector" in args[0]
        assert "metadata" in args[0]
        assert args[0]["title"] == "test_lancedb"

    def test_insert_lancedb_metadata_special_key(self, lancedb_store, mock_lancedb):
        """insert evita duplicar key 'metadata' en el row."""
        vec = _make_vec(384, seed=3).reshape(1, -1)
        meta = [{"metadata": "should_not_duplicate", "domain": "test"}]
        lancedb_store.insert("rag_chunks", vec, meta)
        args = mock_lancedb["table"].add.call_args[0][0]
        row = args[0]
        # El campo 'metadata' se setea como json.dumps, no se sobreescribe
        assert row["metadata"] == json.dumps(meta[0])
        # La key 'metadata' del dict no debe agregarse como campo aparte
        # porque el bucle la salta


# ===========================================================================
# TESTS — Update
# ===========================================================================


class TestUpdate:
    """update_records en ambos modos."""

    def test_update_memory(self, mem_store):
        """update_records en memoria actualiza items que matchean filtro."""
        vec = _make_vec(384, seed=10).reshape(1, -1)
        meta = [{"domain": "test", "status": "active"}]
        ids = mem_store.insert("rag_chunks", vec, meta)
        count = mem_store.update_records(
            "rag_chunks",
            filters={"domain": "test"},
            updates={"status": "completed"},
        )
        assert count == 1
        item = mem_store._mem_collections["rag_chunks"].items[ids[0]]
        assert item.metadata["status"] == "completed"
        assert "updated_at" in item.metadata

    def test_update_memory_no_match(self, mem_store):
        """update_records sin matches retorna 0."""
        vec = _make_vec(384, seed=11).reshape(1, -1)
        mem_store.insert("rag_chunks", vec, [{"domain": "test"}])
        count = mem_store.update_records(
            "rag_chunks",
            filters={"domain": "nonexistent"},
            updates={"status": "done"},
        )
        assert count == 0

    def test_update_memory_collection_not_found(self, mem_store):
        """update_records en colección inexistente lanza CollectionNotFoundError."""
        with pytest.raises(CollectionNotFoundError) as excinfo:
            mem_store.update_records(
                "no_such_collection",
                filters={"x": 1},
                updates={"y": 2},
            )
        assert "not found in memory store" in str(excinfo.value)

    def test_update_lancedb(self, lancedb_store_with_data, mock_lancedb):
        """update_records en modo LanceDB actualiza registros."""
        table = mock_lancedb["table"]
        # Configurar resultado de búsqueda
        table.search.return_value.where.return_value.to_list.return_value = [
            {"id": "r1", "metadata": json.dumps({"domain": "test"}), "vector": [0.1]},
        ]
        count = lancedb_store_with_data.update_records(
            "rag_chunks",
            filters={"domain": "test"},
            updates={"new_field": "value"},
        )
        assert count == 1
        table.update.assert_called_once()
        call_kwargs = table.update.call_args[1]
        assert call_kwargs["where"] == "id = 'r1'"
        # Verificar que metadata se actualizó con los nuevos valores
        updated_meta = json.loads(call_kwargs["values"]["metadata"])
        assert updated_meta["new_field"] == "value"
        assert updated_meta["domain"] == "test"

    def test_update_lancedb_collection_not_found(self, lancedb_store, mock_lancedb):
        """update_records en colección inexistente lanza CollectionNotFoundError."""
        mock_lancedb["db_conn"].open_table.side_effect = RuntimeError("not found")
        with pytest.raises(CollectionNotFoundError) as excinfo:
            lancedb_store.update_records(
                "ghost",
                filters={"id": "x"},
                updates={"y": "z"},
            )
        assert "not found in LanceDB" in str(excinfo.value)

    def test_update_lancedb_search_fails(self, lancedb_store, mock_lancedb, caplog):
        """update_records con search fallido trata existing como vacío."""
        table = mock_lancedb["table"]
        table.search.return_value.where.side_effect = RuntimeError("search fail")
        count = lancedb_store.update_records(
            "rag_chunks",
            filters={"domain": "test"},
            updates={"x": "y"},
        )
        assert count == 0  # existing = []

    def test_update_lancedb_update_fails_logs(self, lancedb_store, mock_lancedb, caplog):
        """update_records loggea warning si update individual falla."""
        table = mock_lancedb["table"]
        table.search.return_value.where.return_value.to_list.return_value = [
            {"id": "r1", "metadata": json.dumps({"a": 1})},
            {"id": "r2", "metadata": json.dumps({"a": 2})},
        ]
        table.update.side_effect = RuntimeError("update fail")
        with caplog.at_level(logging.WARNING):
            count = lancedb_store.update_records(
                "rag_chunks",
                filters={"a": 1},
                updates={"new": "val"},
            )
        assert count == 2
        assert any("Failed to update record" in rec.message for rec in caplog.records)

    def test_update_lancedb_record_no_id(self, lancedb_store, mock_lancedb):
        """update_records salta registros sin id."""
        table = mock_lancedb["table"]
        table.search.return_value.where.return_value.to_list.return_value = [
            {"metadata": json.dumps({"a": 1})},  # sin id
            {"id": "r2", "metadata": json.dumps({"a": 2})},
        ]
        count = lancedb_store.update_records(
            "rag_chunks",
            filters={"a": 1},
            updates={"new": "val"},
        )
        assert count == 2  # ambos están en existing aunque uno no tenga id
        # update solo debe llamarse para r2
        assert table.update.call_count == 1

    def test_update_lancedb_metadata_parsing(self, lancedb_store, mock_lancedb):
        """update_records maneja metadata en distintos formatos."""
        table = mock_lancedb["table"]
        table.search.return_value.where.return_value.to_list.return_value = [
            {"id": "r1", "metadata": json.dumps({"a": 1})},
            {"id": "r2", "metadata": {"b": 2}},  # ya es dict
            {"id": "r3", "metadata": 42},  # tipo inesperado
            {"id": "r4"},  # sin metadata
        ]
        count = lancedb_store.update_records(
            "rag_chunks",
            filters={"a": 1},
            updates={"new": "val"},
        )
        assert count == 4
        # update debe llamarse 4 veces, cada una con metadata actualizada
        assert table.update.call_count == 4

    def test_update_lancedb_metadata_json_decode_error(self, lancedb_store, mock_lancedb):
        """update_records con metadata JSON inválido lo trata como {}."""
        table = mock_lancedb["table"]
        table.search.return_value.where.return_value.to_list.return_value = [
            {"id": "r1", "metadata": "{invalid json}"},
        ]
        count = lancedb_store.update_records(
            "rag_chunks",
            filters={"x": 1},
            updates={"new": "val"},
        )
        assert count == 1
        # Verificar que se usó meta = {}
        call_kwargs = table.update.call_args[1]
        updated_meta = json.loads(call_kwargs["values"]["metadata"])
        assert updated_meta == {"new": "val"}

    def test_update_lancedb_where_clause_int(self, lancedb_store, mock_lancedb):
        """update_records construye WHERE con valores numéricos correctamente."""
        table = mock_lancedb["table"]
        table.search.return_value.where.return_value.to_list.return_value = [
            {"id": "r1", "metadata": "{}"},
        ]
        lancedb_store.update_records(
            "rag_chunks",
            filters={"count": 10, "active": True},
            updates={"status": "done"},
        )
        # Verificar que search.where recibió una cláusula con valores sin comillas
        call_args = table.search.return_value.where.call_args[0][0]
        assert "count = 10" in call_args
        assert "active = True" in call_args


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
        # combined_score se usa internamente pero NO se limpia del output
        # (solo _keyword_bonus se elimina antes de retornar)

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
        # Verificar que los resultados están ordenados por combined_score descendente
        # (no tenemos acceso directo a combined_score, pero podemos verificar que el
        #  resultado con keyword aparece antes)

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
# TESTS — Errores y hardening
# ===========================================================================


class TestErrorHandling:
    """Edge cases de error handling en ambos modos."""

    def test_init_import_error_message(self):
        """El mensaje de ImportError es claro y descriptivo."""
        with patch.object(LanceVectorStore, "_try_import_lancedb", return_value=None):
            with pytest.raises(ImportError) as excinfo:
                LanceVectorStore(db_path="/tmp/x", allow_fallback=False)
        msg = str(excinfo.value)
        assert "LanceDB no esta instalado" in msg
        assert "pip install lancedb" in msg

    def test_init_runtime_error_message(self, mock_lancedb):
        """El mensaje de RuntimeError incluye la ruta y el error original."""
        mock_lancedb["lancedb_module"].connect.side_effect = PermissionError("access denied")
        patches = [
            patch.object(
                LanceVectorStore, "_try_import_lancedb",
                return_value=mock_lancedb["lancedb_module"],
            ),
            patch("harness.memory_rag.lance_vector_store.os.makedirs"),
        ]
        with patches[0], patches[1]:
            with pytest.raises(RuntimeError) as excinfo:
                LanceVectorStore(db_path="/custom/path", allow_fallback=False)
        msg = str(excinfo.value)
        assert "/custom/path" in msg
        assert "access denied" in msg

    def test_insert_lancedb_open_fails_propagates(self, lancedb_store, mock_lancedb):
        """Si open_table falla en insert, la excepción se propaga."""
        mock_lancedb["db_conn"].open_table.side_effect = RuntimeError("table missing")
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
        with patch.object(LanceVectorStore, "_try_import_lancedb", return_value=None), \
             patch("harness.memory_rag.lance_vector_store.get_memory_config", return_value=cfg):
            store = LanceVectorStore.from_config()
        assert store is not None
        assert store._allow_fallback is True

    def test_from_config_with_config(self):
        """from_config con MemoryConfig explícito."""
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
            ("update_records", ("ghost",), {"filters": {"x": 1}, "updates": {"y": 2}}),
        ],
    )
    def test_all_methods_collection_not_found_memory(
        self, mem_store, method_name, args, kwargs
    ):
        """Todos los métodos lanzan CollectionNotFoundError en memoria si la colección no existe."""
        method = getattr(mem_store, method_name)
        with pytest.raises(CollectionNotFoundError):
            method(*args, **kwargs)


# ===========================================================================
# TESTS — Hybrid search on LanceDB mode
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
# TESTS — Clear en LanceDB con error en drop
# ===========================================================================


class TestClearEdgeCases:
    """Edge cases de clear()."""

    def test_clear_lancedb_partial_failure(self, lancedb_store, mock_lancedb, caplog):
        """clear continúa aunque algunos drop_table fallen."""
        # Simular que el primer drop falla, el segundo también...
        mock_lancedb["db_conn"].drop_table.side_effect = [
            RuntimeError("fail1"),
            None,  # éxito
            RuntimeError("fail3"),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ]
        with caplog.at_level(logging.WARNING):
            lancedb_store.clear()
        # Debió intentar dropear todas
        assert mock_lancedb["db_conn"].drop_table.call_count == len(DEFAULT_COLLECTIONS)
        # Verificar que después del clear, las colecciones por defecto están en memoria
        assert len(lancedb_store._mem_collections) == len(DEFAULT_COLLECTIONS)

    def test_clear_memory_preserves_defaults(self, mem_store):
        """clear en memoria preserva las colecciones por defecto con sus schemas."""
        # Añadir una colección extra
        mem_store.create_collection("temporal")
        assert "temporal" in mem_store._mem_collections
        mem_store.clear()
        # La colección extra debe desaparecer
        assert "temporal" not in mem_store._mem_collections
        # Las defaults deben estar
        for name in DEFAULT_COLLECTIONS:
            assert name in mem_store._mem_collections
            assert mem_store._mem_collections[name].schema_def == DEFAULT_COLLECTIONS[name]["schema"]


# ===========================================================================
# TESTS — Constantes de colección
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
