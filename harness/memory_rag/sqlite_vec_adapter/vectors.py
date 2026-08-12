"""Operaciones con vectores para ``SQLiteVecAdapter`` (mixin).

Extraido mecanicamente de ``sqlite_vec_adapter.py`` (regla AGR < 500 lineas).
Sin cambios de logica ni de firmas.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

import numpy as np

from ..sqlite_vec_utils import (
    _META_TABLE,
    CollectionNotFoundError,
    DimensionMismatchError,
    SQLiteVecError,
    VectorRecord,
    _cosine_similarity,
)

logger = logging.getLogger("harness.memory_rag.sqlite_vec_adapter")


class _VectorOpsMixin:
    """Metodos de insercion, busqueda y CRUD de vectores."""

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
            ids: Lista opcional de IDs. Si es None, se generan "vec_{i}".
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
