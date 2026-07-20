"""
MockVectorStore — Implementacion falsa de LanceVectorStore para tests.

Reemplaza LanceDB real con almacenamiento en memoria (dicts+lists).
Permite:
- Session-scoped fixtures (sin depender de LanceDB instalado)
- Tests paralelos con pytest-xdist (sin lock de base de datos)
- Ejecucion sin dependencia de lancedb

Cubre la interfaz usada por: AgentBus, SemanticCache, TaskManager, etc.

Compatibilidad:
  - Metodos nativos: create_collection, add, search, delete, list_tables, clear
  - Alias compatibles con LanceVectorStore: insert, list_collections,
    get_collection_stats, hybrid_search, update_records, delete_collection
  - Acepta tanto List[float] como np.ndarray en search/insert
  - Items almacenados como objetos con atributos .metadata, .vector, .created_at
    (compatible con SemanticCache que accede item.metadata directamente)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)

# Tipo aceptado para vectores: lista de floats o numpy array
VectorLike = Union[List[float], "np.ndarray"]


@dataclass
class _MockStoredItem:
    """Item almacenado en memoria, compatible con _StoredItem de LanceVectorStore.

    Atributos de acceso directo usados por SemanticCache:
      - .metadata: dict con metadatos del item
      - .vector: Optional[np.ndarray]
      - .created_at: str ISO timestamp
    """

    id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    vector: Optional[np.ndarray] = None
    created_at: str = ""


@dataclass
class _MemCollection:
    """Coleccion en memoria imitando una tabla LanceDB."""

    name: str
    items: Dict[str, _MockStoredItem] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Metodos internos
    # ------------------------------------------------------------------

    def search(
        self, vector: List[float], top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Busqueda simulada (retorna items por orden de insercion).

        Args:
            vector: Vector de consulta (ignorado en modo simulado).
            top_k: Maximo numero de resultados.

        Returns:
            Lista de dicts con key, id, score, metadata, created_at.
        """
        results: List[Dict[str, Any]] = []
        for _key, item in list(self.items.items())[:top_k]:
            results.append(
                {
                    "key": item.id,
                    "id": item.id,
                    "score": 1.0,
                    "metadata": item.metadata,
                    "vector": item.vector.tolist() if item.vector is not None else None,
                    "created_at": item.created_at,
                }
            )
        return results

    def add(self, items: List[Dict[str, Any]]) -> List[str]:
        """Agregar items a la coleccion.

        Args:
            items: Lista de dicts con datos a almacenar.

        Returns:
            Lista de IDs insertados.
        """
        ids: List[str] = []
        now = datetime.now(timezone.utc).isoformat()
        for item_dict in items:
            item_id = item_dict.get("id", str(uuid.uuid4()))
            ids.append(item_id)

            # Extraer metadata del dict (todo excepto campos internos)
            raw_vector = item_dict.get("vector", None)
            vec: Optional[np.ndarray] = None
            if raw_vector is not None:
                if isinstance(raw_vector, np.ndarray):
                    vec = raw_vector
                elif isinstance(raw_vector, (list, tuple)):
                    vec = np.array(raw_vector, dtype=np.float32)

            meta = {
                k: v
                for k, v in item_dict.items()
                if k not in ("id", "vector", "created_at")
            }
            # Si hay key 'metadata' explicita, usarla como base
            if "metadata" in item_dict:
                explicit_meta = item_dict["metadata"]
                if isinstance(explicit_meta, dict):
                    explicit_meta.update(meta)
                    meta = explicit_meta

            created = item_dict.get("created_at", now)

            self.items[item_id] = _MockStoredItem(
                id=item_id,
                metadata=meta,
                vector=vec,
                created_at=created,
            )
        return ids

    def delete(self, key: str) -> None:
        """Eliminar item por key.

        Args:
            key: Identificador del item a eliminar.
        """
        self.items.pop(key, None)


class MockVectorStore:
    """VectorStore simulado sin dependencia de LanceDB.

    Usage:
        store = MockVectorStore()
        store.create_collection("test")
        store.add("test", [{"id": "1", "text": "hello"}])
        results = store.search("test", [0.1]*384)

    Compatible con la interfaz de LanceVectorStore:
        store.insert("col", vectors, metadata)
        store.search("col", query_vector, top_k, filters)
        store.list_collections()
        store.get_collection_stats("col")
        store.hybrid_search("col", query_vector, keyword, top_k)
        store.update_records("col", filters, updates)
        store.delete_collection("col")
    """

    def __init__(self, db_path: str = "", allow_fallback: bool = True):
        """Inicializa el MockVectorStore.

        Args:
            db_path: Ruta simulada (solo para compatibilidad con LanceVectorStore).
            allow_fallback: Ignorado, siempre disponible.
        """
        self._collections: Dict[str, _MemCollection] = {}
        # Alias para compatibilidad con SemanticCache que accede a _mem_collections
        self._mem_collections: Dict[str, _MemCollection] = self._collections
        self._lancedb_available = False
        self._db = None
        self.db_path = db_path or "/tmp/mock_vector_store"
        self._allow_fallback = allow_fallback
        self._embedding_dim: int = 384

    # ==================================================================
    # API nativa (definida por MockVectorStore)
    # ==================================================================

    def create_collection(self, name: str) -> None:
        """Crear una coleccion en memoria.

        Args:
            name: Nombre de la coleccion.
        """
        if name not in self._collections:
            self._collections[name] = _MemCollection(name=name)
            logger.debug("MockVectorStore: created collection '%s'", name)

    def add(
        self, collection: str, items: List[Dict[str, Any]]
    ) -> None:
        """Agregar items a una coleccion.

        Args:
            collection: Nombre de la coleccion.
            items: Lista de dicts con los datos a insertar.
        """
        if collection not in self._collections:
            self.create_collection(collection)
        self._collections[collection].add(items)

    def search(
        self,
        collection: str,
        vector: VectorLike,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Buscar en coleccion con filtros opcionales.

        Args:
            collection: Nombre de la coleccion.
            vector: Vector de consulta (List[float] o np.ndarray).
            top_k: Maximo numero de resultados.
            filters: Dict opcional de campo -> valor para filtrar.

        Returns:
            Lista de resultados con id, score, metadata, created_at.
        """
        col = self._collections.get(collection)
        if not col:
            return []

        # Convertir numpy array a lista si es necesario
        vec_list: List[float] = (
            vector.tolist() if isinstance(vector, np.ndarray) else list(vector)
        )

        results = col.search(vec_list, top_k=top_k)

        if filters:
            filtered = []
            for r in results:
                match = True
                meta = r.get("metadata", {})
                if not isinstance(meta, dict):
                    meta = {}
                for k, v in filters.items():
                    if r.get(k) != v and meta.get(k) != v:
                        match = False
                        break
                if match:
                    filtered.append(r)
            return filtered
        return results

    def delete(self, collection: str, key: str) -> None:
        """Eliminar item de coleccion.

        Args:
            collection: Nombre de la coleccion.
            key: Identificador del item a eliminar.
        """
        col = self._collections.get(collection)
        if col:
            col.delete(key)

    def list_tables(self) -> List[str]:
        """Listar colecciones disponibles.

        Returns:
            Lista de nombres de colecciones.
        """
        return list(self._collections.keys())

    def clear(self) -> None:
        """Limpiar todas las colecciones."""
        self._collections.clear()

    # ==================================================================
    # Alias de compatibilidad con LanceVectorStore
    # ==================================================================

    def insert(
        self,
        collection: str,
        vectors: np.ndarray,
        metadata: List[Dict[str, Any]],
    ) -> List[str]:
        """Insertar vectores con metadatos (compatible con LanceVectorStore).

        Args:
            collection: Nombre de la coleccion.
            vectors: Array numpy 2-D de forma (n_items, dim).
            metadata: Lista de dicts, uno por vector.

        Returns:
            Lista de IDs insertados.
        """
        n = vectors.shape[0]
        if n == 0:
            return []

        ids: List[str] = []
        items: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat()
        for i in range(n):
            rid = str(uuid.uuid4())
            ids.append(rid)
            meta: Dict[str, Any] = metadata[i] if i < len(metadata) else {}
            item: Dict[str, Any] = {
                "id": rid,
                "vector": vectors[i].tolist(),
                "metadata": meta,
                "created_at": now,
            }
            # Merge metadata fields into top-level for searchability
            item.update(meta)
            items.append(item)

        self.add(collection, items)

        if n > 0 and vectors.shape[1] > self._embedding_dim:
            self._embedding_dim = vectors.shape[1]

        return ids

    def list_collections(self) -> List[str]:
        """Listar colecciones disponibles (alias de list_tables).

        Returns:
            Lista de nombres de colecciones.
        """
        return self.list_tables()

    def get_collection_stats(
        self, name: str
    ) -> Dict[str, Any]:
        """Retorna estadisticas de una coleccion.

        Args:
            name: Nombre de la coleccion.

        Returns:
            Dict con name, item_count, schema, last_updated.

        Raises:
            ValueError: Si la coleccion no existe.
        """
        col = self._collections.get(name)
        if not col:
            raise ValueError(
                f"Collection '{name}' not found in memory store."
            )
        return {
            "name": name,
            "item_count": len(col.items),
            "schema": {},
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def hybrid_search(
        self,
        collection: str,
        query_vector: np.ndarray,
        keyword_filter: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Busqueda hibrida combinando similitud vectorial con keyword.

        Args:
            collection: Nombre de la coleccion.
            query_vector: Vector de consulta.
            keyword_filter: Keyword para filtrar.
            top_k: Maximo numero de resultados.

        Returns:
            Lista de resultados ordenados por relevancia.
        """
        # Obtener resultados vectoriales
        results = self.search(collection, query_vector, top_k=top_k * 3)

        kw_lower = keyword_filter.lower()

        def _keyword_score(item: Dict[str, Any]) -> float:
            meta = item.get("metadata", {})
            if not isinstance(meta, dict):
                meta = {}
            fields_to_check = [
                str(meta.get("domain", "")),
                str(meta.get("title", "")),
                str(meta.get("chunk", "")),
                " ".join(meta.get("tags", [])),
            ]
            text = " ".join(fields_to_check).lower()
            return 1.0 if kw_lower in text else 0.0

        for item in results:
            item["_keyword_bonus"] = _keyword_score(item)
            score = item.get("score", 0.0)
            bonus = item["_keyword_bonus"]
            item["combined_score"] = 0.7 * score + 0.3 * bonus

        reranked = sorted(
            results,
            key=lambda x: x.get("combined_score", 0.0),
            reverse=True,
        )

        # Limpiar campos internos
        for item in reranked:
            item.pop("_keyword_bonus", None)

        return reranked[:top_k]

    def update_records(
        self,
        collection: str,
        filters: Dict[str, Any],
        updates: Dict[str, Any],
    ) -> int:
        """Actualizar registros que coinciden con filtros.

        Args:
            collection: Nombre de la coleccion.
            filters: Dict campo -> valor para seleccionar registros.
            updates: Dict campo -> valor con los cambios.

        Returns:
            Numero de registros actualizados.

        Raises:
            ValueError: Si la coleccion no existe.
        """
        col = self._collections.get(collection)
        if not col:
            raise ValueError(
                f"Collection '{collection}' not found in memory store."
            )

        count = 0
        now = datetime.now(timezone.utc).isoformat()
        for item in col.items.values():
            match = all(
                item.metadata.get(k) == v
                for k, v in filters.items()
            )
            if match:
                item.metadata.update(updates)
                item.metadata["updated_at"] = now
                count += 1

        return count

    def delete_collection(self, name: str) -> None:
        """Eliminar una coleccion completa.

        Args:
            name: Nombre de la coleccion a eliminar.
        """
        self._collections.pop(name, None)
