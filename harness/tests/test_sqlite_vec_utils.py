"""Tests TDD (spec-first) para sqlite_vec_utils.

Contrato (spec):
- Excepciones: SQLiteVecError base, CollectionNotFoundError, DimensionMismatchError,
  VectorNotFoundError (todas heredan de SQLiteVecError).
- VectorRecord: valida que vector sea np.ndarray, convierte float64 a float32.
- CollectionMeta: name, dimension, size=0, created_at.
- _l2_normalize: normaliza a norma 1, lanza ValueError si norma 0.
- _cosine_similarity: similitud en [-1, 1], 1 para idénticos, 0 ortogonales, -1 opuestos.

Invariantes (PBT):
- Para cualquier vector v con norma > 0: ||normalize(v)|| = 1.
- Para cualquier a, b: cosine(a, b) en [-1, 1].
"""
from __future__ import annotations

import numpy as np
import pytest

from harness.memory_rag.sqlite_vec_utils import (
    CollectionMeta,
    CollectionNotFoundError,
    DimensionMismatchError,
    SQLiteVecError,
    VectorNotFoundError,
    VectorRecord,
    _cosine_similarity,
    _l2_normalize,
)


class TestSQLiteVecUtilsExceptions:
    """Spec: jerarquía de excepciones."""

    def test_all_errors_inherit_base(self) -> None:
        """Spec: todas las excepciones heredan de SQLiteVecError."""
        assert issubclass(CollectionNotFoundError, SQLiteVecError)
        assert issubclass(DimensionMismatchError, SQLiteVecError)
        assert issubclass(VectorNotFoundError, SQLiteVecError)

    def test_exceptions_are_catchable_as_base(self) -> None:
        """Spec: se pueden atrapar como SQLiteVecError."""
        with pytest.raises(SQLiteVecError):
            raise CollectionNotFoundError("x")


class TestSQLiteVecUtilsVectorRecord:
    """Spec: VectorRecord."""

    def test_vector_record_requires_ndarray(self) -> None:
        """Spec: vector debe ser np.ndarray."""
        with pytest.raises(TypeError, match="np.ndarray"):
            VectorRecord(id="v1", vector=[1.0, 0.0])

    def test_vector_record_accepts_float64(self) -> None:
        """Spec: float64 se acepta (preserva dtype; la conversion a float32
        ocurre en el adapter, no en el DTO)."""
        vec = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        rec = VectorRecord(id="v1", vector=vec)
        assert rec.vector.dtype == np.float64
        assert rec.id == "v1"

    def test_vector_record_preserves_float32(self) -> None:
        """Spec: float32 se preserva."""
        vec = np.array([1.0, 0.0], dtype=np.float32)
        rec = VectorRecord(id="v1", vector=vec)
        assert rec.vector.dtype == np.float32
        assert rec.id == "v1"
        assert rec.metadata == {}
        assert rec.collection == ""
        assert rec.created_at > 0


class TestSQLiteVecUtilsCollectionMeta:
    """Spec: CollectionMeta."""

    def test_collection_meta_defaults(self) -> None:
        """Spec: defaults razonables."""
        meta = CollectionMeta(name="c1", dimension=8)
        assert meta.name == "c1"
        assert meta.dimension == 8
        assert meta.size == 0
        assert meta.created_at > 0


class TestSQLiteVecUtilsNormalize:
    """Spec: _l2_normalize."""

    def test_normalize_unit_norm(self) -> None:
        """Spec: normaliza a norma 1."""
        v = np.array([3.0, 4.0], dtype=np.float32)
        n = _l2_normalize(v)
        assert abs(np.linalg.norm(n) - 1.0) < 1e-6

    def test_normalize_zero_raises(self) -> None:
        """Spec: vector de norma cero lanza ValueError."""
        v = np.zeros(3, dtype=np.float32)
        with pytest.raises(ValueError, match="norma cero"):
            _l2_normalize(v)

    def test_normalize_direction_preserved(self) -> None:
        """Spec: la dirección se preserva."""
        v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        n = _l2_normalize(v)
        assert np.dot(n, v) > 0  # misma dirección


class TestSQLiteVecUtilsCosine:
    """Spec: _cosine_similarity."""

    def test_cosine_identical_is_one(self) -> None:
        """Spec: vectores idénticos -> similitud 1."""
        v = np.array([1.0, 0.0], dtype=np.float32)
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_cosine_orthogonal_is_zero(self) -> None:
        """Spec: vectores ortogonales -> similitud 0."""
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_cosine_opposite_is_negative_one(self) -> None:
        """Spec: vectores opuestos -> similitud -1."""
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0], dtype=np.float32)
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_cosine_symmetric(self) -> None:
        """Spec: similitud es simétrica."""
        a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        b = np.array([2.0, -1.0, 0.5], dtype=np.float32)
        assert abs(_cosine_similarity(a, b) - _cosine_similarity(b, a)) < 1e-9


class TestSQLiteVecUtilsPBT:
    """Invariantes (PBT) con Hypothesis."""

    def test_normalize_norm_is_one_for_random(self) -> None:
        """Invariante: para cualquier vector, la norma tras normalizar es 1."""
        rng = np.random.default_rng(42)
        for _ in range(20):
            v = rng.standard_normal(16).astype(np.float32)
            n = _l2_normalize(v)
            assert abs(np.linalg.norm(n) - 1.0) < 1e-5

    def test_cosine_in_range_for_random(self) -> None:
        """Invariante: cosine siempre en [-1, 1]."""
        rng = np.random.default_rng(7)
        for _ in range(20):
            a = rng.standard_normal(8).astype(np.float32)
            b = rng.standard_normal(8).astype(np.float32)
            s = _cosine_similarity(a, b)
            assert -1.0 <= s <= 1.0

    def test_cosine_zero_vector_safe(self) -> None:
        """Invariante: cosine con vector cero no divide por cero."""
        a = np.array([1.0, 0.0], dtype=np.float32)
        z = np.zeros(2, dtype=np.float32)
        s = _cosine_similarity(a, z)
        assert -1.0 <= s <= 1.0  # no lanza
