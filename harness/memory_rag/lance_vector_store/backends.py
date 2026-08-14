"""Mixins de backend para ``LanceVectorStore``.

Extraido mecanicamente de ``lance_vector_store.py`` (regla AGR < 500 lineas).
Contiene los metodos privados de backend (LanceDB e in-memory) como mixins
para que ``LanceVectorStore`` (en ``core.py``) conserve la misma API publica
y privada sin cambios de logica ni de firmas.

Imports relativos: ``..`` apunta a ``harness.memory_rag`` (modulos hermanos).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np

from ..lance_migration import generate_sample_row, serialize_for_schema
from ..lance_schemas import DEFAULT_COLLECTIONS
from .exceptions import CollectionNotFoundError
from .models import _Collection, _StoredItem

logger = logging.getLogger("harness.memory_rag.lance_vector_store")


class _LanceDBBackendMixin:
    """Metodos privados de backend LanceDB para ``LanceVectorStore``."""

    @staticmethod
    def _try_import_lancedb():
        """Safely attempt to import lancedb; return None on failure."""
        try:
            import lancedb  # type: ignore[import-untyped]
            return lancedb
        except ImportError:
            return None

    def _ensure_lancedb_collections(self) -> None:
        """Create default tables in LanceDB if they don't exist.

        LanceDB 0.33+ requires schema to be defined at creation time.
        Uses generate_sample_row() from lance_migration.py (que a su vez
        usa _infer_schema_recursive() para inferencia recursiva de tipos).
        """
        if not self._lancedb_available or self._db is None:
            return
        existing = set(self._db.list_tables().tables)
        for name in DEFAULT_COLLECTIONS:
            if name in existing:
                continue
            sample = generate_sample_row(name)
            try:
                self._db.create_table(name, data=[sample], mode="create")
                tbl = self._db.open_table(name)
                tbl.delete("id = 'init'")
                logger.info("Created LanceDB table '%s' with full schema", name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not create table '%s': %s", name, exc)

    def _insert_lancedb(
        self,
        collection: str,
        vectors: np.ndarray,
        metadata: list[dict[str, Any]],
        now: str,
    ) -> list[str]:
        """Inserta vectores en una tabla LanceDB (helper de ``insert``)."""
        tbl = self._db.open_table(collection)  # type: ignore[union-attr]
        rows: list[dict[str, Any]] = []
        ids: list[str] = []
        for i in range(vectors.shape[0]):
            rid = str(uuid.uuid4())
            ids.append(rid)
            # Build row with serialized metadata fields for schema compatibility
            row: dict[str, Any] = {
                "id": rid,
                "vector": vectors[i].tolist(),
                "metadata": json.dumps(metadata[i]),
                "created_at": now,
            }
            for k, v in metadata[i].items():
                if k == "metadata":
                    continue
                row[k] = serialize_for_schema(v)
            rows.append(row)
        tbl.add(rows)
        return ids

    def _update_records_lancedb(
        self,
        collection: str,
        filters: dict[str, Any],
        updates: dict[str, Any],
    ) -> int:
        """Actualiza registros en LanceDB (helper de ``update_records``)."""
        try:
            tbl = self._db.open_table(collection)
        except Exception as exc:
            raise CollectionNotFoundError(
                f"Collection '{collection}' not found in LanceDB: {exc}"
            ) from exc

        # Construir clausula WHERE desde los filtros
        conditions = []
        for k, v in filters.items():
            if isinstance(v, str):
                conditions.append(f"{k} = '{v}'")
            else:
                conditions.append(f"{k} = {v}")
        where_clause = " AND ".join(conditions)

        # Leer registros existentes para actualizar metadata JSON
        try:
            existing = tbl.search().where(where_clause).to_list()
        except Exception:  # noqa: BLE001
            existing = []

        for record in existing:
            record_id = record.get("id")
            if not record_id:
                continue

            # Actualizar metadata JSON si existe
            meta_raw = record.get("metadata", "{}")
            if isinstance(meta_raw, str):
                try:
                    meta = json.loads(meta_raw)
                except (json.JSONDecodeError, TypeError):
                    meta = {}
            elif isinstance(meta_raw, dict):
                meta = meta_raw
            else:
                meta = {}

            meta.update(updates)

            # Actualizar: top-level + metadata JSON
            update_values = {
                "metadata": json.dumps(meta),
                **updates,
            }

            # Limpiar solo 'vector' del top-level (metadata debe actualizarse)
            update_values.pop("vector", None)

            try:
                tbl.update(where=f"id = '{record_id}'", values=update_values)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to update record %s in '%s': %s",
                    record_id, collection, exc,
                )

        return len(existing)

    def _search_lancedb(
        self,
        collection: str,
        query_vector: np.ndarray,
        top_k: int,
        filters: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Busqueda por similitud en LanceDB (helper de ``search``)."""
        try:
            tbl = self._db.open_table(collection)
        except Exception as exc:
            raise CollectionNotFoundError(
                f"Collection '{collection}' not found in LanceDB: {exc}"
            ) from exc

        query_list = query_vector.tolist()
        results = tbl.search(query_list).limit(top_k).to_list()

        # Convert metadata from JSON string to dict for filtering
        for r in results:
            m = r.get("metadata", r)
            if isinstance(m, str):
                try:
                    r["metadata"] = json.loads(m)
                except (json.JSONDecodeError, TypeError):
                    r["metadata"] = {}

        # Apply post-filtering for metadata fields if LanceDB doesn't natively support them
        if filters:
            results = [
                r
                for r in results
                if all(
                    r.get(k) == v or r.get("metadata", {}).get(k) == v
                    for k, v in filters.items()
                )
            ][:top_k]

        out: list[dict[str, Any]] = []
        for r in results:
            meta = r.get("metadata", {})
            out.append(
                {
                    "id": r.get("id", ""),
                    "score": r.get("_distance", r.get("score", 0.0)),
                    "metadata": meta,
                    "created_at": r.get("created_at", ""),
                }
            )
        return out

    def _stats_lancedb(self, name: str) -> dict[str, Any]:
        """Estadisticas de una tabla LanceDB (helper de ``get_collection_stats``)."""
        try:
            tbl = self._db.open_table(name)
        except Exception as exc:
            raise CollectionNotFoundError(
                f"Collection '{name}' not found: {exc}"
            ) from exc
        # Usar count_rows() para item_count y to_arrow() para datos
        item_count = tbl.count_rows()
        schema = DEFAULT_COLLECTIONS.get(name, {}).get("schema", {})
        last_up = ""
        if item_count > 0:
            try:
                # Obtener solo la ultima fila para timestamp
                arrow_table = tbl.to_arrow()
                if arrow_table.num_rows > 0:
                    last_row = arrow_table.slice(arrow_table.num_rows - 1, 1)
                    if "created_at" in arrow_table.column_names:
                        last_up = str(last_row.column("created_at")[0].as_py())
            except Exception:  # noqa: BLE001
                last_up = ""
        return {
            "name": name,
            "item_count": item_count,
            "schema": schema,
            "last_updated": last_up,
        }


class _MemoryBackendMixin:
    """Metodos privados de backend in-memory para ``LanceVectorStore``."""

    def _insert_memory(
        self,
        collection: str,
        vectors: np.ndarray,
        metadata: list[dict[str, Any]],
        now: str,
    ) -> list[str]:
        """Inserta vectores en el store in-memory (helper de ``insert``)."""
        col = self._get_or_create_mem_collection(collection)
        ids: list[str] = []
        for i in range(vectors.shape[0]):
            rid = str(uuid.uuid4())
            ids.append(rid)
            col.items[rid] = _StoredItem(
                id=rid,
                vector=vectors[i],
                metadata=metadata[i],
                created_at=now,
            )
        col.last_updated = now

        self._embedding_dim = max(self._embedding_dim, vectors.shape[1])

        return ids

    def _get_or_create_mem_collection(self, name: str) -> _Collection:
        """Ensure in-memory collection exists; create on demand."""
        if name not in self._mem_collections:
            self._mem_collections[name] = _Collection(
                name=name,
                schema_def={},
                last_updated=datetime.now(UTC).isoformat(),
            )
        return self._mem_collections[name]

    def _update_records_memory(
        self,
        collection: str,
        filters: dict[str, Any],
        updates: dict[str, Any],
    ) -> int:
        """Actualiza registros in-memory (helper de ``update_records``)."""
        if collection not in self._mem_collections:
            raise CollectionNotFoundError(
                f"Collection '{collection}' not found in memory store."
            )

        col = self._mem_collections[collection]
        count = 0
        now = datetime.now(UTC).isoformat()

        for item in col.items.values():
            match = all(
                item.metadata.get(k) == v for k, v in filters.items()
            )
            if match:
                item.metadata.update(updates)
                item.metadata["updated_at"] = now
                count += 1

        if count > 0:
            col.last_updated = now

        return count

    def _search_memory(
        self,
        collection: str,
        query_vector: np.ndarray,
        top_k: int,
        filters: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Busqueda por similitud in-memory (helper de ``search``)."""
        if collection not in self._mem_collections:
            raise CollectionNotFoundError(
                f"Collection '{collection}' not found in memory store."
            )

        col = self._mem_collections[collection]
        if not col.items:
            return []

        # Pre-filter items
        candidates = list(col.items.values())
        if filters:
            filtered: list[_StoredItem] = []
            for item in candidates:
                match = all(
                    item.metadata.get(k) == v for k, v in filters.items()
                )
                if match:
                    filtered.append(item)
            candidates = filtered

        if not candidates:
            return []

        # Compute cosine similarity (GPU acelerada si batch > 10k)
        vectors = np.array(
            [c.vector for c in candidates if c.vector is not None]
        )
        if vectors.size == 0:
            return []

        if vectors.shape[0] >= 10000:
            # GPU-accelerated search for large batches
            from harness.gpu_optimize import gpu_similarity_search
            results = gpu_similarity_search(
                query_vector, vectors, top_k=top_k
            )
            top_indices = np.array([r[0] for r in results])
            sims = np.array([r[1] for r in results])
        else:
            # CPU path for small batches (faster for <10k)
            q_norm = query_vector / (np.linalg.norm(query_vector) + 1e-12)
            sims = vectors @ q_norm
            top_indices = np.argsort(sims)[-top_k:][::-1]

        results: list[dict[str, Any]] = []
        for idx in top_indices:
            item = candidates[idx]
            results.append(
                {
                    "id": item.id,
                    "score": float(sims[idx]),
                    "metadata": item.metadata,
                    "created_at": item.created_at,
                }
            )
        return results

    def _stats_memory(self, name: str) -> dict[str, Any]:
        """Estadisticas de una coleccion in-memory (helper de ``get_collection_stats``)."""
        if name not in self._mem_collections:
            raise CollectionNotFoundError(
                f"Collection '{name}' not found in memory store."
            )
        col = self._mem_collections[name]
        return {
            "name": name,
            "item_count": len(col.items),
            "schema": col.schema_def,
            "last_updated": col.last_updated,
        }
