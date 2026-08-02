"""SQLiteVecAdapter â€” Backend vectorial ligero via sqlite-vec.

Proporciona almacenamiento vectorial portable sin dependencias externas.
Ideal para edge computing, dispositivos sin GPU, y entornos offline.

Basado en: github.com/asg017/sqlite-vec (extension vectorial para SQLite).

Ventajas:
- Zero dependencias externas (solo sqlite3 + numpy).
- Base de datos portable (un solo .db file).
- Sincronizable via Git (archivos pequenos).
- Ideal para CI/CD y tests sin infraestructura.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Self

import numpy as np

try:
    import sqlite_vec
except ImportError:
    sqlite_vec = None  # type: ignore[assignment]

from harness.memory_rag.sqlite_vec_utils import (
    _DEFAULT_DIMENSION,
    _META_TABLE,
    _VEC_TABLE_PREFIX,
    HAS_SQLITE_VEC,
    CollectionMeta,
    CollectionNotFoundError,
    DimensionMismatchError,
    SQLiteVecError,
    VectorRecord,
    _cosine_similarity,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adaptador principal
# ---------------------------------------------------------------------------

class SQLiteVecAdapter:
    """Adaptador vectorial portable con backend sqlite-vec o fallback Python puro.

    Almacena vectores en tablas SQLite con metadatos JSON.
    Proporciona busqueda kNN por cosine similarity y operaciones
    CRUD con proteccion thread-safe.

    Args:
        db_path: Ruta al archivo .db (o \":memory:\" para base volatil).
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

        Args:
            collection: Nombre de la coleccion.

        Returns:
            Nombre de tabla SQLite con prefijo.
        """
        safe = collection.replace('"', '""').replace("'", "''")
        return f"{_VEC_TABLE_PREFIX}{safe}"

    # ------------------------------------------------------------------
    # CRUD de colecciones
    # ------------------------------------------------------------------

    def create_collection(
        self,
        name: str,
        dimension: int | None = None,
    ) -> CollectionMeta:
        """Crea una nueva coleccion de vectores.

        Args:
            name: Nombre unico de la coleccion.
            dimension: Dimensionalidad de los vectores (default: configuracion global).

        Returns:
            CollectionMeta con los datos de la coleccion creada.

        Raises:
            SQLiteVecError: Si la coleccion ya existe o hay error de BD.
        """
        dim = dimension if dimension is not None else self._default_dim
        if dim < 1:
            raise ValueError(f"Dimension debe ser >= 1, got {dim}")

        with self._lock:
            self._assert_initialized()
            if self._collection_exists(name):
                raise SQLiteVecError(f"Coleccion '{name}' ya existe")
            try:
                assert self._conn is not None
                now = time.time()
                self._conn.execute(
                    # tabla interna constante, valores parametrizados
                    f"INSERT INTO {_META_TABLE} (name, dimension, created_at) VALUES (?, ?, ?)",  # nosec B608
                    (name, dim, now),
                )
                tbl = self._vec_table_name(name)
                self._conn.execute(
                    f"CREATE TABLE {tbl} ("
                    "  id         TEXT PRIMARY KEY,"
                    "  vector     BLOB NOT NULL,"
                    "  metadata   TEXT DEFAULT '{}',"
                    "  created_at REAL NOT NULL"
                    ")"
                )
                self._conn.commit()
                logger.info("[SQLiteVec] Coleccion '%s' creada (dim=%d)", name, dim)
                return CollectionMeta(name=name, dimension=dim, size=0, created_at=now)
            except sqlite3.Error as exc:
                self._conn.rollback()
                raise SQLiteVecError(
                    f"[SQLiteVec::create_collection] Error creando '{name}': {exc}"
                ) from exc

    def delete_collection(self, name: str) -> bool:
        """Elimina una coleccion y todos sus vectores.

        Args:
            name: Nombre de la coleccion a eliminar.

        Returns:
            True si se elimino, False si no existia.
        """
        with self._lock:
            if not self._collection_exists(name):
                logger.warning("[SQLiteVec::delete_collection] Coleccion '%s' no encontrada", name)
                return False
            try:
                assert self._conn is not None
                tbl = self._vec_table_name(name)
                # tbl sanitizado por _vec_table_name
                self._conn.execute(f"DROP TABLE IF EXISTS {tbl}")  # nosec B608
                # tabla interna, valor parametrizado
                self._conn.execute(f"DELETE FROM {_META_TABLE} WHERE name = ?", (name,))  # nosec B608
                self._conn.commit()
                logger.info("[SQLiteVec] Coleccion '%s' eliminada", name)
                return True
            except sqlite3.Error as exc:
                self._conn.rollback()
                raise SQLiteVecError(
                    f"[SQLiteVec::delete_collection] Error eliminando '{name}': {exc}"
                ) from exc

    def list_collections(self) -> list[CollectionMeta]:
        """Lista todas las colecciones registradas.

        Returns:
            Lista de CollectionMeta con el tamano actualizado.
        """
        with self._lock:
            self._assert_initialized()
            try:
                assert self._conn is not None
                cursor = self._conn.execute(
                    # tabla interna constante
                    f"SELECT name, dimension, created_at FROM {_META_TABLE} ORDER BY name"  # nosec B608
                )
                collections: list[CollectionMeta] = []
                for row in cursor.fetchall():
                    name, dim, created = row
                    size = self._count_vectors_internal(name)
                    collections.append(CollectionMeta(name=name, dimension=dim, size=size, created_at=created))
                return collections
            except sqlite3.Error as exc:
                raise SQLiteVecError(
                    f"[SQLiteVec::list_collections] Error listando colecciones: {exc}"
                ) from exc

    def get_collection(self, name: str) -> CollectionMeta | None:
        """Obtiene metadatos de una coleccion especifica.

        Args:
            name: Nombre de la coleccion.

        Returns:
            CollectionMeta si existe, None en caso contrario.
        """
        collections = self.list_collections()
        for col in collections:
            if col.name == name:
                return col
        return None

    def _collection_exists(self, name: str) -> bool:
        """Verifica si una coleccion existe en metadatos.

        Args:
            name: Nombre de la coleccion.

        Returns:
            True si existe.
        """
        try:
            assert self._conn is not None
            cursor = self._conn.execute(
                # tabla interna, valor parametrizado
                f"SELECT COUNT(*) FROM {_META_TABLE} WHERE name = ?", (name,)  # nosec B608
            )
            row = cursor.fetchone()
            return row is not None and row[0] > 0
        except sqlite3.Error:
            return False

    def _assert_collection_exists(self, name: str) -> None:
        """Lanza error si la coleccion no existe.

        Args:
            name: Nombre de la coleccion.

        Raises:
            CollectionNotFoundError: Si no existe.
        """
        if not self._collection_exists(name):
            raise CollectionNotFoundError(f"Coleccion '{name}' no encontrada")

    def _assert_initialized(self) -> None:
        """Lanza error si el adaptador no esta inicializado.

        Raises:
            SQLiteVecError: Si no se ha llamado a initialize().
        """
        if not self._initialized or self._conn is None:
            raise SQLiteVecError("Adaptador no inicializado. Llame a initialize() primero.")

    # ------------------------------------------------------------------
    # InserciÃ³n de vectores
    # ------------------------------------------------------------------

    def add_vector(
        self,
        collection: str,
        vector_id: str,
        vector: list[float] | np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> VectorRecord:
        """Inserta un vector individual en una coleccion.

        Args:
            collection: Nombre de la coleccion destino.
            vector_id: Identificador unico del vector.
            vector: Lista o arreglo numpy de coordenadas.
            metadata: Diccionario opcional de metadatos.

        Returns:
            VectorRecord insertado.

        Raises:
            CollectionNotFoundError: Si la coleccion no existe.
            DimensionMismatchError: Si la dimension no coincide.
        """
        vec = np.asarray(vector, dtype=np.float32)
        meta = metadata or {}
        with self._lock:
            self._assert_collection_exists(collection)
            dim = self._get_collection_dimension(collection)
            if len(vec) != dim:
                raise DimensionMismatchError(
                    f"Dimension del vector {len(vec)} != dimension coleccion {dim}"
                )
            try:
                assert self._conn is not None
                tbl = self._vec_table_name(collection)
                now = time.time()
                blob = vec.tobytes()
                meta_json = json.dumps(meta, ensure_ascii=False, default=str)
                self._conn.execute(
                    f"INSERT OR REPLACE INTO {tbl} (id, vector, metadata, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (vector_id, blob, meta_json, now),
                )
                self._conn.commit()
                record = VectorRecord(
                    id=vector_id,
                    vector=vec,
                    metadata=meta,
                    collection=collection,
                    created_at=now,
                )
                logger.debug("[SQLiteVec] Vector '%s' agregado a '%s'", vector_id, collection)
                return record
            except sqlite3.Error as exc:
                self._conn.rollback()
                raise SQLiteVecError(
                    f"[SQLiteVec::add_vector] Error insertando '{vector_id}' en '{collection}': {exc}"
                ) from exc

    def batch_add(
        self,
        collection: str,
        vectors: list[tuple[str, list[float] | np.ndarray]],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> list[VectorRecord]:
        """Inserta multiples vectores en una sola transaccion.

        Args:
            collection: Nombre de la coleccion destino.
            vectors: Lista de tuplas (id, vector).
            metadatas: Lista opcional de metadatos (debe coincidir en longitud).

        Returns:
            Lista de VectorRecord insertados.

        Raises:
            CollectionNotFoundError: Si la coleccion no existe.
            DimensionMismatchError: Si alguna dimension no coincide.
        """
        metas = metadatas or [{}] * len(vectors)
        if len(metas) != len(vectors):
            raise ValueError(f"metadatas length {len(metas)} != vectors length {len(vectors)}")
        with self._lock:
            self._assert_collection_exists(collection)
            dim = self._get_collection_dimension(collection)
            records: list[VectorRecord] = []
            try:
                assert self._conn is not None
                tbl = self._vec_table_name(collection)
                data_rows: list[tuple[str, bytes, str, float]] = []
                now = time.time()
                for (vid, vec_raw), meta in zip(vectors, metas):
                    vec = np.asarray(vec_raw, dtype=np.float32)
                    if len(vec) != dim:
                        raise DimensionMismatchError(
                            f"Vector '{vid}' dim {len(vec)} != {dim}"
                        )
                    blob = vec.tobytes()
                    meta_json = json.dumps(meta, ensure_ascii=False, default=str)
                    data_rows.append((vid, blob, meta_json, now))
                    records.append(VectorRecord(
                        id=vid, vector=vec, metadata=meta,
                        collection=collection, created_at=now,
                    ))
                self._conn.executemany(
                    f"INSERT OR REPLACE INTO {tbl} (id, vector, metadata, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    data_rows,
                )
                self._conn.commit()
                logger.info("[SQLiteVec] Batch %d vectores insertados en '%s'", len(records), collection)
                return records
            except (sqlite3.Error, DimensionMismatchError) as exc:
                self._conn.rollback()
                raise SQLiteVecError(
                    f"[SQLiteVec::batch_add] Error en batch para '{collection}': {exc}"
                ) from exc

    def add_vectors(
        self,
        collection: str,
        embeddings: np.ndarray,
        ids: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        """Inserta vectores desde una matriz numpy (batch optimizado).

        Args:
            collection: Nombre de la coleccion destino.
            embeddings: Matriz numpy (N, D).
            ids: Lista opcional de IDs. Si es None, se generan \"vec_{i}\".
            metadatas: Lista opcional de metadatos.

        Returns:
            Lista de IDs insertados.

        Raises:
            CollectionNotFoundError: Si la coleccion no existe.
        """
        n = embeddings.shape[0]
        if ids is None:
            ids = [f"vec_{i}" for i in range(n)]
        if metadatas is None:
            metadatas = [{}] * n
        vectors = list(zip(ids, [embeddings[i] for i in range(n)]))
        records = self.batch_add(collection, vectors, metadatas)
        return [r.id for r in records]

    # ------------------------------------------------------------------
    # Consulta / busqueda
    # ------------------------------------------------------------------

    def search(
        self,
        collection: str,
        query: list[float] | np.ndarray,
        k: int = 10,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """Busqueda kNN por cosine similarity.

        Args:
            collection: Nombre de la coleccion.
            query: Vector de consulta.
            k: Numero de vecinos a retornar (default 10).

        Returns:
            Lista de tuplas (id, score, metadata) ordenadas por similitud
            descendente. Score es cosine similarity en [-1, 1].

        Raises:
            CollectionNotFoundError: Si la coleccion no existe.
        """
        q = np.asarray(query, dtype=np.float32)
        with self._lock:
            self._assert_collection_exists(collection)
            dim = self._get_collection_dimension(collection)
            if len(q) != dim:
                raise DimensionMismatchError(
                    f"Dimension query {len(q)} != {dim}"
                )
            try:
                assert self._conn is not None
                tbl = self._vec_table_name(collection)
                cursor = self._conn.execute(
                    # tbl sanitizado por _vec_table_name
                    f"SELECT id, vector, metadata FROM {tbl}"  # nosec B608
                )
                results: list[tuple[str, float, dict[str, Any]]] = []
                for row in cursor.fetchall():
                    vid, blob, meta_json = row
                                    #if isinstance(vid, memoryview):
                    #    vid = bytes(vid).decode('utf-8') if isinstance(vid, bytes) else str(vid)
                    vec = np.frombuffer(blob, dtype=np.float32)
                    score = _cosine_similarity(q, vec)
                    meta: dict[str, Any] = {}
                    if meta_json:
                        try:
                            meta = json.loads(meta_json) if isinstance(meta_json, str) else json.loads(bytes(meta_json).decode("utf-8"))
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            meta = {"_raw": str(meta_json)}
                    results.append((vid, score, meta))
                # Ordenar descendente por score
                results.sort(key=lambda x: x[1], reverse=True)
                return results[:k]
            except sqlite3.Error as exc:
                raise SQLiteVecError(
                    f"[SQLiteVec::search] Error buscando en '{collection}': {exc}"
                ) from exc

    # ------------------------------------------------------------------
    # Lectura / eliminacion de vectores individuales
    # ------------------------------------------------------------------

    def get_vector(self, collection: str, vector_id: str) -> VectorRecord | None:
        """Obtiene un vector por su ID.

        Args:
            collection: Nombre de la coleccion.
            vector_id: Identificador del vector.

        Returns:
            VectorRecord si existe, None en caso contrario.
        """
        with self._lock:
            if not self._collection_exists(collection):
                return None
            try:
                assert self._conn is not None
                tbl = self._vec_table_name(collection)
                cursor = self._conn.execute(
                    # tbl sanitizado, valor parametrizado
                    f"SELECT id, vector, metadata, created_at FROM {tbl} WHERE id = ?",  # nosec B608
                    (vector_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                vid, blob, meta_json, created = row
                vec = np.frombuffer(blob, dtype=np.float32)
                meta: dict[str, Any] = {}
                if meta_json:
                    try:
                        meta = json.loads(meta_json) if isinstance(meta_json, str) else json.loads(bytes(meta_json).decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        meta = {"_raw": str(meta_json)}
                return VectorRecord(
                    id=vid, vector=vec, metadata=meta,
                    collection=collection, created_at=created,
                )
            except sqlite3.Error as exc:
                raise SQLiteVecError(
                    f"[SQLiteVec::get_vector] Error leyendo '{vector_id}' en '{collection}': {exc}"
                ) from exc

    def delete_vector(self, collection: str, vector_id: str) -> bool:
        """Elimina un vector por su ID.

        Args:
            collection: Nombre de la coleccion.
            vector_id: Identificador del vector.

        Returns:
            True si se elimino, False si no existia.
        """
        with self._lock:
            if not self._collection_exists(collection):
                return False
            try:
                assert self._conn is not None
                tbl = self._vec_table_name(collection)
                cursor = self._conn.execute(
                    # tbl sanitizado, valor parametrizado
                    f"DELETE FROM {tbl} WHERE id = ?", (vector_id,)  # nosec B608
                )
                deleted = cursor.rowcount > 0
                self._conn.commit()
                if deleted:
                    logger.debug("[SQLiteVec] Vector '%s' eliminado de '%s'", vector_id, collection)
                return deleted
            except sqlite3.Error as exc:
                self._conn.rollback()
                raise SQLiteVecError(
                    f"[SQLiteVec::delete_vector] Error eliminando '{vector_id}' en '{collection}': {exc}"
                ) from exc

    # ------------------------------------------------------------------
    # Conteo
    # ------------------------------------------------------------------

    def count(self, collection: str) -> int:
        """Retorna la cantidad total de vectores en una coleccion.

        Args:
            collection: Nombre de la coleccion.

        Returns:
            Numero de vectores (0 si la coleccion no existe).
        """
        with self._lock:
            return self._count_vectors_internal(collection)

    def _count_vectors_internal(self, collection: str) -> int:
        """Conteo interno sin lock (debe llamarse con lock tomado).

        Args:
            collection: Nombre de la coleccion.

        Returns:
            Numero de vectores en la coleccion.
        """
        if not self._collection_exists(collection):
            return 0
        try:
            assert self._conn is not None
            tbl = self._vec_table_name(collection)
            # tbl sanitizado por _vec_table_name
            cursor = self._conn.execute(f"SELECT COUNT(*) FROM {tbl}")  # nosec B608
            row = cursor.fetchone()
            return int(row[0]) if row else 0
        except sqlite3.Error:
            return 0

    def total_count(self) -> int:
        """Retorna la cantidad total de vectores en todas las colecciones.

        Returns:
            Suma de vectores en todas las colecciones.
        """
        total = 0
        for col in self.list_collections():
            total += col.size
        return total

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    def _get_collection_dimension(self, name: str) -> int:
        """Obtiene la dimension de una coleccion desde metadatos.

        Args:
            name: Nombre de la coleccion.

        Returns:
            Dimension entera.

        Raises:
            CollectionNotFoundError: Si no existe.
        """
        assert self._conn is not None
        cursor = self._conn.execute(
            # tabla interna, valor parametrizado
            f"SELECT dimension FROM {_META_TABLE} WHERE name = ?", (name,)  # nosec B608
        )
        row = cursor.fetchone()
        if row is None:
            raise CollectionNotFoundError(f"Coleccion '{name}' no encontrada")
        return int(row[0])

    def _get_collection_dimension_safe(self, name: str) -> int | None:
        """Obtiene dimension sin lanzar excepcion.

        Args:
            name: Nombre de la coleccion.

        Returns:
            Dimension o None si no existe.
        """
        try:
            return self._get_collection_dimension(name)
        except CollectionNotFoundError:
            return None

    # ------------------------------------------------------------------
    # Serializacion / export
    # ------------------------------------------------------------------

    def export_collection(
        self,
        collection: str,
        include_vectors: bool = True,
    ) -> list[dict[str, Any]]:
        """Exporta una coleccion completa como lista de diccionarios.

        Util para backup o migracion.

        Args:
            collection: Nombre de la coleccion.
            include_vectors: Si incluye los vectores (default True).

        Returns:
            Lista de registros serializables.

        Raises:
            CollectionNotFoundError: Si la coleccion no existe.
        """
        self._assert_collection_exists(collection)
        try:
            assert self._conn is not None
            tbl = self._vec_table_name(collection)
            cursor = self._conn.execute(
                # tbl sanitizado por _vec_table_name
                f"SELECT id, vector, metadata, created_at FROM {tbl}"  # nosec B608
            )
            records: list[dict[str, Any]] = []
            for row in cursor.fetchall():
                vid, blob, meta_json, created = row
                rec: dict[str, Any] = {
                    "id": vid,
                    "metadata": json.loads(meta_json) if isinstance(meta_json, str) else {},
                    "created_at": created,
                }
                if include_vectors:
                    vec = np.frombuffer(blob, dtype=np.float32)
                    rec["vector"] = vec.tolist()
                    rec["dimension"] = len(vec)
                records.append(rec)
            return records
        except sqlite3.Error as exc:
            raise SQLiteVecError(
                f"[SQLiteVec::export_collection] Error exportando '{collection}': {exc}"
            ) from exc

    def import_collection(
        self,
        collection: str,
        records: list[dict[str, Any]],
        dimension: int | None = None,
    ) -> int:
        """Importa registros a una coleccion (debe existir o crearse).

        Args:
            collection: Nombre de la coleccion.
            records: Lista de diccionarios con keys \"id\", \"vector\", \"metadata\".
            dimension: Dimension sobreescribe la deteccion automatica.

        Returns:
            Numero de vectores importados.
        """
        if not self._collection_exists(collection):
            detected_dim = dimension or (len(records[0]["vector"]) if records else self._default_dim)
            self.create_collection(collection, dimension=detected_dim)
        vectors: list[tuple[str, list[float]]] = []
        metadatas: list[dict[str, Any]] = []
        for rec in records:
            vid = rec.get("id", str(hash(str(rec))))
            vec = rec.get("vector", [])
            meta = rec.get("metadata", {})
            vectors.append((vid, vec))
            metadatas.append(meta)
        result = self.batch_add(collection, vectors, metadatas)
        return len(result)

    # ------------------------------------------------------------------
    # Mantenimiento
    # ------------------------------------------------------------------

    def vacuum(self) -> None:
        """Ejecuta VACUUM para recuperar espacio en disco.

        Recomendado despues de muchas eliminaciones.
        """
        with self._lock:
            self._assert_initialized()
            try:
                assert self._conn is not None
                self._conn.execute("VACUUM")
                logger.info("[SQLiteVec] VACUUM completado.")
            except sqlite3.Error as exc:
                raise SQLiteVecError(
                    f"[SQLiteVec::vacuum] Error en VACUUM: {exc}"
                ) from exc

    def stats(self) -> dict[str, Any]:
        """Retorna estadisticas generales del adaptador.

        Returns:
            Diccionario con informacion de uso.
        """
        cols = self.list_collections()
        return {
            "collections": len(cols),
            "total_vectors": sum(c.size for c in cols),
            "db_path": str(self._db_path),
            "sqlite_vec_enabled": self._vec_enabled,
            "initialized": self._initialized,
            "collections_detail": [
                {"name": c.name, "dimension": c.dimension, "size": c.size}
                for c in cols
            ],
        }
