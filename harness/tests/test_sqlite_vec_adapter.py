"""Tests para SQLiteVecAdapter — backend vectorial portable (sqlite-vec o fallback).

Cubre:
- Lifecycle (initialize, close, is_connected, context manager)
- Gestion de colecciones (create, delete, list, get, exists)
- Insercion de vectores (add_vector, batch_add, add_vectors)
- Busqueda kNN con cosine similarity
- CRUD de vectores individuales (get, delete, count)
- Utilidades (_l2_normalize, _cosine_similarity, _vec_table_name)
- Excepciones (DimensionMismatchError, CollectionNotFoundError)
"""
from __future__ import annotations

import threading
from typing import Any

import numpy as np
import pytest

from harness.memory_rag.sqlite_vec_adapter import SQLiteVecAdapter
from harness.memory_rag.sqlite_vec_utils import (
    CollectionMeta,
    CollectionNotFoundError,
    DimensionMismatchError,
    SQLiteVecError,
    VectorRecord,
    _cosine_similarity,
    _l2_normalize,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_adapter(dim: int = 8) -> SQLiteVecAdapter:
    """Crea un adapter inicializado en :memory:."""
    a = SQLiteVecAdapter(db_path=":memory:", dimension=dim)
    a.initialize()
    return a


def random_vec(dim: int = 8, seed: int = 0) -> np.ndarray:
    """Vector aleatorio normalizado."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestSQLiteVecAdapterLifecycle:
    """Tests del ciclo de vida del adapter."""

    def test_init_does_not_connect(self):
        """__init__ no abre la conexion todavia (lazy)."""
        a = SQLiteVecAdapter()
        assert a._conn is None
        assert a._initialized is False
        assert a.is_connected is False

    def test_initialize_opens_connection(self):
        """initialize() abre la conexion y crea schema."""
        a = SQLiteVecAdapter()
        a.initialize()
        try:
            assert a._conn is not None
            assert a._initialized is True
            assert a.is_connected is True
        finally:
            a.close()

    def test_initialize_idempotent(self):
        """initialize() llamado 2 veces no rompe (idempotente)."""
        a = make_adapter()
        a.initialize()  # 2da vez
        assert a.is_connected
        a.close()

    def test_close_releases_connection(self):
        """close() cierra la conexion y limpia estado."""
        a = make_adapter()
        a.close()
        assert a._conn is None
        assert a._initialized is False
        assert a.is_connected is False

    def test_close_idempotent(self):
        """close() llamado multiples veces no rompe."""
        a = make_adapter()
        a.close()
        a.close()  # 2da vez
        a.close()  # 3ra vez
        assert a._conn is None

    def test_context_manager(self):
        """with statement abre y cierra automaticamente."""
        with SQLiteVecAdapter() as a:
            a.create_collection("c1", dimension=8)
            assert a.is_connected
        # Fuera del with: cerrado
        assert not a.is_connected


# ---------------------------------------------------------------------------
# Gestion de colecciones
# ---------------------------------------------------------------------------


class TestSQLiteVecAdapterCollections:
    """Tests de create/delete/list/get collection."""

    def test_create_collection_returns_meta(self):
        """create_collection devuelve CollectionMeta."""
        a = make_adapter(dim=8)
        try:
            meta = a.create_collection("c1", dimension=8)
            assert isinstance(meta, CollectionMeta)
            assert meta.name == "c1"
            assert meta.dimension == 8
            assert meta.size == 0
        finally:
            a.close()

    def test_create_collection_duplicate_raises(self):
        """Crear coleccion duplicada lanza SQLiteVecError."""
        a = make_adapter()
        try:
            a.create_collection("dup", dimension=8)
            with pytest.raises(SQLiteVecError, match="ya existe"):
                a.create_collection("dup", dimension=8)
        finally:
            a.close()

    def test_create_collection_invalid_dim_raises(self):
        """Dimension < 1 lanza ValueError."""
        a = make_adapter()
        try:
            with pytest.raises(ValueError, match="Dimension"):
                a.create_collection("bad", dimension=0)
            with pytest.raises(ValueError, match="Dimension"):
                a.create_collection("bad", dimension=-1)
        finally:
            a.close()

    def test_create_collection_default_dim(self):
        """Sin dimension explicita usa el default del adapter."""
        a = make_adapter(dim=16)
        try:
            meta = a.create_collection("c1")
            assert meta.dimension == 16
        finally:
            a.close()

    def test_list_collections_empty(self):
        """Sin colecciones, lista vacia."""
        a = make_adapter()
        try:
            assert a.list_collections() == []
        finally:
            a.close()

    def test_list_collections_with_data(self):
        """Con colecciones, list_collections devuelve la lista."""
        a = make_adapter()
        try:
            a.create_collection("c1", dimension=8)
            a.create_collection("c2", dimension=16)
            cols = a.list_collections()
            assert len(cols) == 2
            names = {c.name for c in cols}
            assert names == {"c1", "c2"}
        finally:
            a.close()

    def test_get_collection_existing(self):
        """get_collection devuelve meta de coleccion existente."""
        a = make_adapter()
        try:
            a.create_collection("c1", dimension=8)
            meta = a.get_collection("c1")
            assert meta is not None
            assert meta.name == "c1"
            assert meta.dimension == 8
        finally:
            a.close()

    def test_get_collection_unknown_returns_none(self):
        """get_collection de desconocida devuelve None."""
        a = make_adapter()
        try:
            assert a.get_collection("ghost") is None
        finally:
            a.close()

    def test_delete_collection_existing(self):
        """delete_collection devuelve True si existia."""
        a = make_adapter()
        try:
            a.create_collection("temp", dimension=8)
            assert a.delete_collection("temp") is True
            assert a.get_collection("temp") is None
        finally:
            a.close()

    def test_delete_collection_unknown_returns_false(self):
        """delete_collection de desconocida devuelve False."""
        a = make_adapter()
        try:
            assert a.delete_collection("ghost") is False
        finally:
            a.close()


# ---------------------------------------------------------------------------
# Insercion de vectores
# ---------------------------------------------------------------------------


class TestSQLiteVecAdapterInsert:
    """Tests de add_vector, batch_add, add_vectors."""

    def test_add_single_vector(self):
        """Anade un vector y lo recupera con get_vector."""
        a = make_adapter(dim=4)
        try:
            a.create_collection("c1", dimension=4)
            vec = [0.1, 0.2, 0.3, 0.4]
            record = a.add_vector("c1", "v1", vec, metadata={"tag": "test"})
            assert record.id == "v1"
            assert record.collection == "c1"
            assert record.metadata == {"tag": "test"}
            # Recuperar
            got = a.get_vector("c1", "v1")
            assert got is not None
            assert got.id == "v1"
            assert got.metadata == {"tag": "test"}
        finally:
            a.close()

    def test_add_vector_wrong_collection_raises(self):
        """add_vector en coleccion inexistente lanza CollectionNotFoundError."""
        a = make_adapter()
        try:
            with pytest.raises(CollectionNotFoundError):
                a.add_vector("ghost", "v1", [0.1] * 4)
        finally:
            a.close()

    def test_add_vector_wrong_dimension_raises(self):
        """Vector con dimension incorrecta lanza DimensionMismatchError."""
        a = make_adapter(dim=8)
        try:
            a.create_collection("c1", dimension=8)
            with pytest.raises(DimensionMismatchError):
                a.add_vector("c1", "v1", [0.1] * 4)  # 4 != 8
        finally:
            a.close()

    def test_add_vector_upsert(self):
        """Anadir vector con mismo ID lo reemplaza (INSERT OR REPLACE)."""
        a = make_adapter(dim=4)
        try:
            a.create_collection("c1", dimension=4)
            a.add_vector("c1", "v1", [0.1, 0.2, 0.3, 0.4], metadata={"v": 1})
            a.add_vector("c1", "v1", [0.5, 0.6, 0.7, 0.8], metadata={"v": 2})
            got = a.get_vector("c1", "v1")
            assert got is not None
            assert got.metadata == {"v": 2}
            assert a.count("c1") == 1
        finally:
            a.close()

    def test_add_vector_accepts_numpy(self):
        """add_vector acepta np.ndarray ademas de list."""
        a = make_adapter(dim=4)
        try:
            a.create_collection("c1", dimension=4)
            vec = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
            a.add_vector("c1", "v1", vec)
            assert a.count("c1") == 1
        finally:
            a.close()

    def test_batch_add_basic(self):
        """batch_add inserta varios vectores en una transaccion."""
        a = make_adapter(dim=4)
        try:
            a.create_collection("c1", dimension=4)
            vectors = [(f"v{i}", [0.1 * i, 0.2 * i, 0.3 * i, 0.4 * i]) for i in range(1, 6)]
            records = a.batch_add("c1", vectors)
            assert len(records) == 5
            assert a.count("c1") == 5
        finally:
            a.close()

    def test_batch_add_with_metadatas(self):
        """batch_add con metadatos explicitos."""
        a = make_adapter(dim=4)
        try:
            a.create_collection("c1", dimension=4)
            vectors = [("v1", [0.1, 0.2, 0.3, 0.4]), ("v2", [0.5, 0.6, 0.7, 0.8])]
            metas = [{"k": 1}, {"k": 2}]
            records = a.batch_add("c1", vectors, metadatas=metas)
            assert len(records) == 2
            assert records[0].metadata == {"k": 1}
            assert records[1].metadata == {"k": 2}
        finally:
            a.close()

    def test_batch_add_metadata_length_mismatch_raises(self):
        """metadatas con longitud != vectors lanza ValueError."""
        a = make_adapter()
        try:
            a.create_collection("c1", dimension=4)
            vectors = [("v1", [0.1, 0.2, 0.3, 0.4]), ("v2", [0.5, 0.6, 0.7, 0.8])]
            with pytest.raises(ValueError, match="length"):
                a.batch_add("c1", vectors, metadatas=[{"k": 1}])  # 1 meta, 2 vectores
        finally:
            a.close()

    def test_add_vectors_batch(self):
        """add_vectors (variante) inserta vectores desde np.ndarray (N, D)."""
        a = make_adapter(dim=4)
        try:
            a.create_collection("c1", dimension=4)
            embeddings = np.array(
                [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]],
                dtype=np.float32,
            )
            ids = a.add_vectors("c1", embeddings, ids=["v1", "v2"])
            assert len(ids) == 2
            assert "v1" in ids
            assert "v2" in ids
            assert a.count("c1") == 2
        finally:
            a.close()


# ---------------------------------------------------------------------------
# Busqueda
# ---------------------------------------------------------------------------


class TestSQLiteVecAdapterSearch:
    """Tests de search kNN."""

    def test_search_unknown_collection_raises(self):
        """search en coleccion inexistente lanza CollectionNotFoundError."""
        a = make_adapter()
        try:
            with pytest.raises(CollectionNotFoundError):
                a.search("ghost", [0.1] * 4)
        finally:
            a.close()

    def test_search_wrong_dimension_raises(self):
        """search con vector de dimension incorrecta lanza DimensionMismatchError."""
        a = make_adapter(dim=8)
        try:
            a.create_collection("c1", dimension=8)
            with pytest.raises(DimensionMismatchError):
                a.search("c1", [0.1] * 4)
        finally:
            a.close()

    def test_search_empty_returns_empty(self):
        """search en coleccion vacia devuelve lista vacia."""
        a = make_adapter(dim=4)
        try:
            a.create_collection("c1", dimension=4)
            results = a.search("c1", [0.1, 0.2, 0.3, 0.4])
            assert results == []
        finally:
            a.close()

    def test_search_returns_results(self):
        """search devuelve tuplas (id, score, metadata) ordenadas."""
        a = make_adapter(dim=4)
        try:
            a.create_collection("c1", dimension=4)
            a.add_vector("c1", "exact", [1.0, 0.0, 0.0, 0.0])
            a.add_vector("c1", "ortho", [0.0, 1.0, 0.0, 0.0])
            results = a.search("c1", [1.0, 0.0, 0.0, 0.0], k=2)
            assert len(results) == 2
            # El primero debe ser 'exact' (similitud = 1.0)
            assert results[0][0] == "exact"
            assert results[0][1] > 0.99
            # El segundo es 'ortho' (similitud = 0)
            assert results[1][0] == "ortho"
        finally:
            a.close()

    def test_search_k_limits_results(self):
        """k limita el numero de resultados."""
        a = make_adapter(dim=4)
        try:
            a.create_collection("c1", dimension=4)
            for i in range(5):
                a.add_vector("c1", f"v{i}", random_vec(4, seed=i).tolist())
            results = a.search("c1", random_vec(4, seed=99).tolist(), k=3)
            assert len(results) <= 3
        finally:
            a.close()


# ---------------------------------------------------------------------------
# CRUD vectores individuales
# ---------------------------------------------------------------------------


class TestSQLiteVecAdapterCRUD:
    """Tests de get/delete/count de vectores individuales."""

    def test_get_vector_unknown_collection_returns_none(self):
        """get_vector en coleccion inexistente devuelve None (no raise)."""
        a = make_adapter()
        try:
            assert a.get_vector("ghost", "v1") is None
        finally:
            a.close()

    def test_get_vector_unknown_id_returns_none(self):
        """get_vector de id inexistente devuelve None."""
        a = make_adapter()
        try:
            a.create_collection("c1", dimension=4)
            assert a.get_vector("c1", "nope") is None
        finally:
            a.close()

    def test_delete_vector_existing(self):
        """delete_vector devuelve True si existia."""
        a = make_adapter()
        try:
            a.create_collection("c1", dimension=4)
            a.add_vector("c1", "v1", [0.1, 0.2, 0.3, 0.4])
            assert a.delete_vector("c1", "v1") is True
            assert a.get_vector("c1", "v1") is None
        finally:
            a.close()

    def test_delete_vector_unknown_returns_false(self):
        """delete_vector de id inexistente devuelve False."""
        a = make_adapter()
        try:
            a.create_collection("c1", dimension=4)
            assert a.delete_vector("c1", "nope") is False
        finally:
            a.close()

    def test_count_collection_empty(self):
        """count en coleccion vacia devuelve 0."""
        a = make_adapter()
        try:
            a.create_collection("c1", dimension=4)
            assert a.count("c1") == 0
        finally:
            a.close()

    def test_count_after_inserts(self):
        """count refleja el numero real de vectores."""
        a = make_adapter()
        try:
            a.create_collection("c1", dimension=4)
            for i in range(3):
                a.add_vector("c1", f"v{i}", [0.1, 0.2, 0.3, 0.4])
            assert a.count("c1") == 3
        finally:
            a.close()

    def test_count_unknown_collection_returns_zero(self):
        """count en coleccion inexistente devuelve 0 (no raise)."""
        a = make_adapter()
        try:
            assert a.count("ghost") == 0
        finally:
            a.close()

    def test_total_count_sums_all_collections(self):
        """total_count suma todos los vectores de todas las colecciones."""
        a = make_adapter()
        try:
            a.create_collection("c1", dimension=4)
            a.create_collection("c2", dimension=4)
            a.add_vector("c1", "a", [0.1, 0.2, 0.3, 0.4])
            a.add_vector("c1", "b", [0.5, 0.6, 0.7, 0.8])
            a.add_vector("c2", "x", [0.1, 0.2, 0.3, 0.4])
            assert a.total_count() == 3
        finally:
            a.close()

    def test_vacuum_does_not_fail(self):
        """vacuum() ejecuta sin error (puede no hacer nada en :memory:)."""
        a = make_adapter()
        try:
            a.create_collection("c1", dimension=4)
            a.add_vector("c1", "v1", [0.1, 0.2, 0.3, 0.4])
            a.vacuum()  # no debe fallar
        finally:
            a.close()


# ---------------------------------------------------------------------------
# Concurrencia
# ---------------------------------------------------------------------------


class TestSQLiteVecAdapterThreadSafety:
    """Verifica thread-safety del adapter."""

    def test_concurrent_add_vectors(self):
        """Multiples hilos anadiendo vectores sin corrupcion."""
        a = make_adapter(dim=4)
        try:
            a.create_collection("c1", dimension=4)
            threads = []
            for i in range(20):
                t = threading.Thread(
                    target=a.add_vector,
                    args=("c1", f"v{i}", [0.1 * i, 0.2, 0.3, 0.4]),
                )
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
            assert a.count("c1") == 20
        finally:
            a.close()

    def test_concurrent_searches(self):
        """Multiples hilos haciendo search en paralelo."""
        a = make_adapter(dim=4)
        try:
            a.create_collection("c1", dimension=4)
            a.add_vector("c1", "v1", [1.0, 0.0, 0.0, 0.0])
            results_all: list[list[Any]] = []
            lock = threading.Lock()

            def search():
                results = a.search("c1", [1.0, 0.0, 0.0, 0.0], k=1)
                with lock:
                    results_all.append(results)

            threads = [threading.Thread(target=search) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert len(results_all) == 10
            assert all(len(r) == 1 for r in results_all)
        finally:
            a.close()


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


class TestSQLiteVecUtils:
    """Tests de las funciones de utilidad."""

    def test_l2_normalize_basic(self):
        """Vector se normaliza a norma 1."""
        v = np.array([3.0, 4.0, 0.0], dtype=np.float32)
        n = _l2_normalize(v)
        assert abs(np.linalg.norm(n) - 1.0) < 1e-6

    def test_l2_normalize_zero_vector_raises(self):
        """Vector de norma cero lanza ValueError."""
        v = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        with pytest.raises(ValueError, match="norma cero"):
            _l2_normalize(v)

    def test_cosine_similarity_identical(self):
        """Vectores identicos tienen similitud 1."""
        v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self):
        """Vectores ortogonales tienen similitud 0."""
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_cosine_similarity_opposite(self):
        """Vectores opuestos tienen similitud -1."""
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0, 0.0], dtype=np.float32)
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_cosine_similarity_in_range(self):
        """Similitud siempre en [-1, 1]."""
        rng = np.random.default_rng(42)
        for _ in range(20):
            a = rng.standard_normal(8).astype(np.float32)
            b = rng.standard_normal(8).astype(np.float32)
            s = _cosine_similarity(a, b)
            assert -1.0 <= s <= 1.0


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class TestSQLiteVecDTOs:
    """Tests de VectorRecord y CollectionMeta."""

    def test_vector_record_creation(self):
        """VectorRecord se crea con los campos correctos."""
        vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        rec = VectorRecord(id="v1", vector=vec, metadata={"k": 1}, collection="c1")
        assert rec.id == "v1"
        assert np.array_equal(rec.vector, vec)
        assert rec.metadata == {"k": 1}
        assert rec.collection == "c1"
        assert rec.created_at > 0

    def test_vector_record_validates_vector_type(self):
        """VectorRecord rechaza vector que no sea np.ndarray."""
        with pytest.raises(TypeError, match="np.ndarray"):
            VectorRecord(id="v1", vector=[1.0, 0.0, 0.0])  # type: ignore[arg-type]

    def test_vector_record_preserves_dtype(self):
        """VectorRecord preserva el dtype del vector original."""
        vec32 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        rec = VectorRecord(id="v1", vector=vec32)
        assert rec.vector.dtype == np.float32

    def test_collection_meta_defaults(self):
        """CollectionMeta con defaults razonables."""
        meta = CollectionMeta(name="c1", dimension=8)
        assert meta.name == "c1"
        assert meta.dimension == 8
        assert meta.size == 0
        assert meta.created_at > 0
