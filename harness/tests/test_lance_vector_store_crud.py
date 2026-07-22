# pragma: allowlist secret
"""Tests CRUD para LanceVectorStore.

Extraído de test_lance_vector_store.py — pruebas de create_collection(),
list_collections(), delete_collection(), clear(), insert(), update_records()
y edge cases de clear() en ambos modos.
"""
from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import numpy as np
import pytest

from harness.memory_rag.lance_schemas import DEFAULT_COLLECTIONS
from harness.memory_rag.lance_vector_store import (
    CollectionNotFoundError,
    LanceVectorStore,
    VectorStoreError,
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
# Helper local (también definido en conftest.py para disponibilidad en fixtures)
# ===========================================================================


def _make_vec(dim: int = 384, seed: int = 0) -> np.ndarray:
    """Crea un vector unitario normalizado para tests."""
    rng = np.random.RandomState(seed)
    v = rng.randn(dim).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-12)
