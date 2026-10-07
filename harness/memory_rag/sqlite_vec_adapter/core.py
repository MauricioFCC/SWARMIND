"""Clase principal ``SQLiteVecAdapter``.

Extraido mecanicamente de ``sqlite_vec_adapter.py`` (regla AGR < 500 lineas).
La clase conserva la misma API publica y privada; los metodos se reparten
en mixins cohesivos (``collections.py``, ``vectors.py``, ``io_ops.py``).
Sin cambios de logica.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import threading
from pathlib import Path
from typing import Self

try:
    import sqlite_vec
except ImportError:
    sqlite_vec = None  # type: ignore[assignment]

from ..sqlite_vec_utils import (
    _DEFAULT_DIMENSION,
    _META_TABLE,
    _VEC_TABLE_PREFIX,
    HAS_SQLITE_VEC,
    SQLiteVecError,
)
from .collections import _CollectionOpsMixin
from .vectors import _VectorOpsMixin

logger = logging.getLogger("harness.memory_rag.sqlite_vec_adapter")

# Allowlist de identificadores de coleccion (nombres de tabla, CWE-89).
_SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,64}$")


class SQLiteVecAdapter(_CollectionOpsMixin, _VectorOpsMixin):
    """Adaptador vectorial portable con backend sqlite-vec o fallback Python puro.

    Almacena vectores en tablas SQLite con metadatos JSON.
    Proporciona busqueda kNN por cosine similarity y operaciones
    CRUD con proteccion thread-safe.

    Args:
        db_path: Ruta al archivo .db (o ":memory:" para base volatil).
        dimension: Dimension por defecto para nuevas colecciones.
    """

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        dimension: int = _DEFAULT_DIMENSION,
    ) -> None:
        self._db_path: Path = Path(db_path) if db_path != ":memory:" else Path(":memory:")
        self._default_dim: int = dimension
        self._lock: threading.Lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._vec_enabled: bool = HAS_SQLITE_VEC
        self._initialized: bool = False

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> Self:
        """Soporte para 'with' statement."""
        self.initialize()
        return self

    def __exit__(self, *args: object) -> None:
        """Cierra conexion al salir del contexto."""
        self.close()

    # ------------------------------------------------------------------
    # Inicializacion / ciclo de vida
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Inicializa la conexion SQLite y schema interno.

        Abre (o crea) la base de datos, carga la extension sqlite-vec
        si esta disponible, y garantiza la existencia de la tabla de metadatos.

        Raises:
            SQLiteVecError: Si no se puede abrir la base de datos.
        """
        if self._initialized:
            return
        try:
            db_str = ":memory:" if str(self._db_path) == ":memory:" else str(self._db_path.resolve())
            self._conn = sqlite3.connect(db_str, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")

            if self._vec_enabled:
                try:
                    sqlite_vec.load(self._conn)
                    logger.debug("[SQLiteVec] Extension sqlite-vec cargada exitosamente.")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[SQLiteVec] Fallback: fallo carga extension (%s)", exc)
                    self._vec_enabled = False

            self._ensure_meta_table()
            self._initialized = True
            logger.info("[SQLiteVec] Base inicializada en %s (vec=%s)", self._db_path, self._vec_enabled)
        except sqlite3.Error as exc:
            raise SQLiteVecError(
                f"[SQLiteVec::initialize] No se pudo abrir BD en {self._db_path}: {exc}"
            ) from exc

    def close(self) -> None:
        """Cierra la conexion SQLite de forma segura.

        Es seguro llamarlo multiples veces.
        """
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error as exc:
                    logger.warning("[SQLiteVec::close] Error cerrando conexion: %s", exc)
                finally:
                    self._conn = None
                    self._initialized = False

    @property
    def is_connected(self) -> bool:
        """Verifica si la conexion esta activa.

        Returns:
            True si la conexion existe y esta inicializada.
        """
        return self._conn is not None and self._initialized

    # ------------------------------------------------------------------
    # Metadatos de colecciones
    # ------------------------------------------------------------------

    def _ensure_meta_table(self) -> None:
        """Crea la tabla de metadatos si no existe."""
        assert self._conn is not None
        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_META_TABLE} ("
            "  name       TEXT PRIMARY KEY,"
            "  dimension  INTEGER NOT NULL,"
            "  created_at REAL NOT NULL"
            ")"
        )
        self._conn.commit()

    def _vec_table_name(self, collection: str) -> str:
        """Retorna el nombre de tabla interna para una coleccion.

        WHAT: valida ``collection`` contra la allowlist ``[A-Za-z0-9_]{1,64}``
        y devuelve el identificador entre comillas dobles.
        WHY: el nombre se interpola en ``CREATE/DROP/SELECT ... {tbl}``; sin
        allowlist un nombre como ``x"; DROP TABLE y; --`` inyecta SQL (CWE-89).
        WHERE: ``SQLiteVecAdapter._vec_table_name`` (usado por collections/vectors).

        Args:
            collection: Nombre de la coleccion.

        Returns:
            Identificador SQLite citado (``"_vec_<collection>"``).

        Raises:
            SQLiteVecError: Si ``collection`` no cumple la allowlist.
        """
        if not isinstance(collection, str) or not _SAFE_IDENTIFIER_PATTERN.match(collection):
            raise SQLiteVecError(
                "Identificador de coleccion invalido; "
                f"WHAT={collection!r}; "
                "WHY=previene inyeccion SQL en nombres de tabla (CWE-89); "
                "WHERE=_vec_table_name; "
                "EXPECTED=^[A-Za-z0-9_]{1,64}$"
            )
        return f'"{_VEC_TABLE_PREFIX}{collection}"'
