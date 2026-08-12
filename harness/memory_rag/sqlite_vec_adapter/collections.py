"""Operaciones CRUD de colecciones para ``SQLiteVecAdapter`` (mixin).

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
    CollectionMeta,
    CollectionNotFoundError,
    SQLiteVecError,
)

logger = logging.getLogger("harness.memory_rag.sqlite_vec_adapter")


class _CollectionOpsMixin:
    """Metodos de gestion de colecciones para ``SQLiteVecAdapter``."""

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

    def export_records(
        self, collection: str, include_vectors: bool = True
    ) -> list[dict[str, Any]]:
        """Exporta los registros de una coleccion como dicts.

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
            records: Lista de diccionarios con keys "id", "vector", "metadata".
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
