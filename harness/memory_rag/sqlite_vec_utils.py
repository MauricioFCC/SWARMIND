"""
sqlite_vec_utils — Utilidades, excepciones y DTOs para SQLiteVecAdapter.

Extraido de sqlite_vec_adapter.py para mantener modulos < 900 lines.

Incluye:
    - Excepciones especificas (SQLiteVecError, CollectionNotFoundError, etc.)
    - Data Transfer Objects (VectorRecord, CollectionMeta)
    - Funciones de normalizacion y similitud de vectores
    - Constantes compartidas
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Nota: sqlite-vec se carga como extension .dll/.so.
# Si no esta disponible, se usa una implementacion Python pura (lenta).
try:
    import sqlite_vec  # noqa: F401
    HAS_SQLITE_VEC = True
except ImportError:
    HAS_SQLITE_VEC = False
    logger.warning("[SQLiteVec] sqlite-vec no instalado. Usando fallback Python puro.")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_DEFAULT_DIMENSION: int = 384
"""Dimension por defecto (sentence-transformers all-MiniLM-L6-v2)."""

_VEC_TABLE_PREFIX: str = "_vec_"
"""Prefijo para tablas internas de vectores."""

_META_TABLE: str = "_vec_meta"
"""Tabla interna de metadatos de colecciones."""

_COSINE_EPSILON: float = 1e-12
"""Epsilon para evitar division por cero en cosine similarity."""


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------


class SQLiteVecError(Exception):
    """Error base del adaptador SQLiteVec."""


class CollectionNotFoundError(SQLiteVecError):
    """La coleccion solicitada no existe."""


class DimensionMismatchError(SQLiteVecError):
    """La dimension del vector no coincide con la coleccion."""


class VectorNotFoundError(SQLiteVecError):
    """El vector solicitado no existe en la coleccion."""


# ---------------------------------------------------------------------------
# Data Transfer Objects
# ---------------------------------------------------------------------------


@dataclass
class VectorRecord:
    """Registro individual de vector con metadatos.

    Attributes:
        id: Identificador unico del vector (string).
        vector: Arreglo numpy de punto flotante.
        metadata: Diccionario de metadatos asociados.
        collection: Nombre de la coleccion a la que pertenece.
        created_at: Timestamp de creacion (epoch seconds).
    """
    id: str
    vector: np.ndarray
    metadata: Dict[str, Any] = field(default_factory=dict)
    collection: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """Valida tipos basicos post-inicializacion."""
        if not isinstance(self.vector, np.ndarray):
            raise TypeError(f"vector debe ser np.ndarray, got {type(self.vector)}")
        if self.vector.dtype not in (np.float32, np.float64):
            self.vector = self.vector.astype(np.float32)


@dataclass
class CollectionMeta:
    """Metadatos de una coleccion de vectores.

    Attributes:
        name: Nombre de la coleccion.
        dimension: Dimensionalidad de los vectores.
        size: Cantidad de vectores almacenados.
        created_at: Timestamp de creacion.
    """
    name: str
    dimension: int
    size: int = 0
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Utilidades de normalizacion
# ---------------------------------------------------------------------------


def _l2_normalize(vector: np.ndarray) -> np.ndarray:
    """Normaliza un vector por su norma L2 in-place.

    Args:
        vector: Arreglo 1-D numpy.

    Returns:
        Vector normalizado (misma forma, norma ~1.0).

    Raises:
        ValueError: Si el vector tiene norma cero.
    """
    norm = np.linalg.norm(vector)
    if norm < _COSINE_EPSILON:
        raise ValueError("No se puede normalizar un vector de norma cero")
    return vector / norm


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Computa cosine similarity entre dos vectores normalizados.

    Args:
        a: Primer vector (1-D).
        b: Segundo vector (1-D).

    Returns:
        Valor de similitud [-1, 1].
    """
    dot = float(np.dot(a, b))
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    denom = max(norm_a * norm_b, _COSINE_EPSILON)
    return max(-1.0, min(1.0, dot / denom))
