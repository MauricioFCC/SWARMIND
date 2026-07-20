"""Tests para MockVectorStore — cobertura total de la API nativa.

Ejecuta sin dependencia de LanceDB.
Todas las funciones con docstring ES-UTF8.
"""
from __future__ import annotations

import numpy as np
import pytest

from harness.tests.mock_vector_store import MockVectorStore

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def store() -> MockVectorStore:
    """MockVectorStore fresco para cada test."""
    return MockVectorStore()


@pytest.fixture
def populated_store(store: MockVectorStore) -> MockVectorStore:
    """MockVectorStore con datos precargados."""
    store.create_collection("test_col")
    store.add(
        "test_col",
        [
            {"id": "1", "text": "hello", "domain": "test", "tags": []},
            {"id": "2", "text": "world", "domain": "test", "tags": ["rust"]},
            {"id": "3", "text": "foo", "domain": "other", "tags": []},
        ],
    )
    return store


# ===========================================================================
# Tests — create_collection
# ===========================================================================


class TestCreateCollection:
    """Prueba la creacion de colecciones."""

    def test_create_collection(self, store: MockVectorStore) -> None:
        """create_collection agrega una coleccion nueva."""
        store.create_collection("test_col")
        assert "test_col" in store.list_tables()

    def test_create_collection_idempotent(self, store: MockVectorStore) -> None:
        """create_collection es idempotente (no lanza error si ya existe)."""
        store.create_collection("test_col")
        store.create_collection("test_col")  # segunda vez no debe fallar
        assert store.list_tables() == ["test_col"]

    def test_create_collection_multiple(self, store: MockVectorStore) -> None:
        """create_collection permite multiples colecciones."""
        store.create_collection("a")
        store.create_collection("b")
        store.create_collection("c")
        assert set(store.list_tables()) == {"a", "b", "c"}


# ===========================================================================
# Tests — add y search
# ===========================================================================


class TestAddAndSearch:
    """Prueba la insercion y busqueda de items."""

    def test_add_and_search(self, store: MockVectorStore) -> None:
        """add inserta items y search los recupera."""
        store.create_collection("test_col")
        store.add("test_col", [{"id": "1", "text": "hello"}])
        results = store.search("test_col", [0.1] * 384, top_k=5)
        assert len(results) == 1
        assert results[0]["id"] == "1"
        assert results[0]["metadata"]["text"] == "hello"

    def test_add_auto_creates_collection(self, store: MockVectorStore) -> None:
        """add crea la coleccion automaticamente si no existe."""
        store.add("auto_col", [{"id": "1", "data": "test"}])
        assert "auto_col" in store.list_tables()
        results = store.search("auto_col", [0.1] * 384)
        assert len(results) == 1

    def test_search_multiple_items(self, store: MockVectorStore) -> None:
        """search retorna hasta top_k items."""
        store.create_collection("multi")
        items = [{"id": str(i), "val": i} for i in range(10)]
        store.add("multi", items)
        results = store.search("multi", [0.1] * 384, top_k=3)
        assert len(results) == 3

    def test_search_with_numpy_vector(self, store: MockVectorStore) -> None:
        """search acepta np.ndarray como vector de consulta."""
        store.create_collection("np_test")
        store.add("np_test", [{"id": "1", "text": "hello"}])
        vec = np.ones(384, dtype=np.float32)
        results = store.search("np_test", vec, top_k=5)
        assert len(results) == 1

    def test_search_insert_compat(self, store: MockVectorStore) -> None:
        """insert (alias LanceVectorStore) funciona y search lo encuentra."""
        vec = np.ones(384, dtype=np.float32).reshape(1, -1)
        ids = store.insert("compat_col", vec, [{"title": "compat test"}])
        assert len(ids) == 1
        results = store.search("compat_col", vec[0], top_k=5)
        assert len(results) == 1
        assert results[0]["id"] == ids[0]

    def test_insert_empty_returns_empty(self, store: MockVectorStore) -> None:
        """insert con vectores vacios retorna lista vacia."""
        vec = np.empty((0, 384), dtype=np.float32)
        ids = store.insert("empty_test", vec, [])
        assert ids == []


# ===========================================================================
# Tests — search con filtros
# ===========================================================================


class TestSearchWithFilters:
    """Prueba la busqueda con filtros de metadata."""

    def test_search_with_filters(self, populated_store: MockVectorStore) -> None:
        """search con filtros retorna solo items que matchean."""
        results = populated_store.search(
            "test_col", [0.1] * 384, top_k=5, filters={"domain": "test"}
        )
        assert len(results) == 2
        assert all(r["metadata"]["domain"] == "test" for r in results)

    def test_search_with_filter_no_match(
        self, populated_store: MockVectorStore
    ) -> None:
        """search con filtro que no matchea nada retorna vacio."""
        results = populated_store.search(
            "test_col", [0.1] * 384, top_k=5, filters={"domain": "nonexistent"}
        )
        assert results == []

    def test_search_with_filters_none(
        self, populated_store: MockVectorStore
    ) -> None:
        """search con filters=None retorna todos los resultados."""
        results = populated_store.search("test_col", [0.1] * 384, top_k=5, filters=None)
        assert len(results) == 3

    def test_search_with_multiple_filters(
        self, populated_store: MockVectorStore
    ) -> None:
        """search con multiples filtros aplica AND."""
        results = populated_store.search(
            "test_col",
            [0.1] * 384,
            top_k=5,
            filters={"domain": "test", "tags": ["rust"]},
        )
        assert len(results) == 1
        assert results[0]["id"] == "2"


# ===========================================================================
# Tests — delete
# ===========================================================================


class TestDelete:
    """Prueba la eliminacion de items."""

    def test_delete_item(self, populated_store: MockVectorStore) -> None:
        """delete elimina un item por key."""
        populated_store.delete("test_col", "1")
        results = populated_store.search("test_col", [0.1] * 384, top_k=5)
        ids = [r["id"] for r in results]
        assert "1" not in ids

    def test_delete_nonexistent_key(
        self, populated_store: MockVectorStore
    ) -> None:
        """delete de key inexistente no lanza error."""
        populated_store.delete("test_col", "nonexistent")  # no debe explotar

    def test_delete_nonexistent_collection(self, store: MockVectorStore) -> None:
        """delete en coleccion inexistente no lanza error."""
        store.delete("no_such_col", "key")  # no debe explotar


# ===========================================================================
# Tests — list_tables / list_collections
# ===========================================================================


class TestListTables:
    """Prueba el listado de colecciones."""

    def test_list_tables_empty(self, store: MockVectorStore) -> None:
        """list_tables en store vacio retorna lista vacia."""
        assert store.list_tables() == []

    def test_list_tables_after_creation(self, store: MockVectorStore) -> None:
        """list_tables refleja las colecciones creadas."""
        store.create_collection("a")
        store.create_collection("b")
        tables = store.list_tables()
        assert "a" in tables
        assert "b" in tables

    def test_list_collections_alias(self, store: MockVectorStore) -> None:
        """list_collections retorna lo mismo que list_tables."""
        store.create_collection("x")
        assert store.list_collections() == store.list_tables()


# ===========================================================================
# Tests — search en coleccion vacia
# ===========================================================================


class TestSearchEmptyCollection:
    """Prueba la busqueda en colecciones vacias."""

    def test_search_empty_collection(self, store: MockVectorStore) -> None:
        """search en coleccion vacia retorna lista vacia."""
        store.create_collection("empty")
        results = store.search("empty", [0.1] * 384, top_k=5)
        assert results == []

    def test_search_nonexistent_collection(self, store: MockVectorStore) -> None:
        """search en coleccion inexistente retorna lista vacia."""
        results = store.search("ghost", [0.1] * 384, top_k=5)
        assert results == []


# ===========================================================================
# Tests — clear
# ===========================================================================


class TestClear:
    """Prueba la limpieza total del store."""

    def test_clear_removes_all(self, populated_store: MockVectorStore) -> None:
        """clear elimina todas las colecciones."""
        assert len(populated_store.list_tables()) > 0
        populated_store.clear()
        assert populated_store.list_tables() == []

    def test_clear_empty_store(self, store: MockVectorStore) -> None:
        """clear en store vacio no lanza error."""
        store.clear()  # no debe explotar

    def test_clear_then_add(self, store: MockVectorStore) -> None:
        """despues de clear se pueden agregar nuevas colecciones."""
        store.create_collection("temp")
        store.clear()
        store.create_collection("new")
        assert store.list_tables() == ["new"]


# ===========================================================================
# Tests — Compatibilidad con LanceVectorStore
# ===========================================================================


class TestLanceCompat:
    """Prueba los alias de compatibilidad con LanceVectorStore."""

    def test_get_collection_stats(self, populated_store: MockVectorStore) -> None:
        """get_collection_stats retorna metadata de la coleccion."""
        stats = populated_store.get_collection_stats("test_col")
        assert stats["name"] == "test_col"
        assert stats["item_count"] == 3
        assert "schema" in stats
        assert "last_updated" in stats

    def test_get_collection_stats_not_found(self, store: MockVectorStore) -> None:
        """get_collection_stats lanza ValueError si no existe."""
        with pytest.raises(ValueError) as excinfo:
            store.get_collection_stats("ghost")
        assert "not found" in str(excinfo.value)

    def test_hybrid_search(self, populated_store: MockVectorStore) -> None:
        """hybrid_search retorna resultados filtrados por keyword."""
        vec = np.ones(384, dtype=np.float32)
        results = populated_store.hybrid_search(
            "test_col", vec, keyword_filter="rust", top_k=5
        )
        assert len(results) >= 1
        # El item con keyword 'rust' debe tener score combinado mas alto
        assert "_keyword_bonus" not in results[0]

    def test_hybrid_search_empty(self, store: MockVectorStore) -> None:
        """hybrid_search en coleccion vacia retorna vacio."""
        store.create_collection("empty")
        vec = np.ones(384, dtype=np.float32)
        results = store.hybrid_search("empty", vec, "keyword", top_k=5)
        assert results == []

    def test_update_records(self, populated_store: MockVectorStore) -> None:
        """update_records actualiza items que matchean filtro por metadata."""
        count = populated_store.update_records(
            "test_col",
            filters={"domain": "test"},
            updates={"status": "updated"},
        )
        assert count == 2
        results = populated_store.search("test_col", [0.1] * 384, top_k=5)
        updated = [r for r in results if r["metadata"].get("status") == "updated"]
        assert len(updated) == 2

    def test_update_records_collection_not_found(
        self, store: MockVectorStore
    ) -> None:
        """update_records en coleccion inexistente lanza ValueError."""
        with pytest.raises(ValueError) as excinfo:
            store.update_records("ghost", filters={"x": 1}, updates={"y": 2})
        assert "not found" in str(excinfo.value)

    def test_delete_collection(self, populated_store: MockVectorStore) -> None:
        """delete_collection elimina la coleccion completa."""
        populated_store.delete_collection("test_col")
        assert "test_col" not in populated_store.list_tables()

    def test_delete_collection_nonexistent(self, store: MockVectorStore) -> None:
        """delete_collection en coleccion inexistente no falla."""
        store.delete_collection("ghost")  # no debe explotar

    def test_db_path_attribute(self) -> None:
        """MockVectorStore tiene atributo db_path para compatibilidad."""
        vs = MockVectorStore(db_path="/custom/path")
        assert vs.db_path == "/custom/path"

    def test_default_db_path(self) -> None:
        """MockVectorStore sin db_path usa default."""
        vs = MockVectorStore()
        assert "/tmp/mock_vector_store" in vs.db_path
