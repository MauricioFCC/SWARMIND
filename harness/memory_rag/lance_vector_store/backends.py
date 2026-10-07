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
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np

from ..lance_migration import generate_sample_row, serialize_for_schema
from ..lance_schemas import DEFAULT_COLLECTIONS
from .exceptions import CollectionNotFoundError
from .models import _Collection, _StoredItem

logger = logging.getLogger("harness.memory_rag.lance_vector_store")

# Allowlist de nombres de campo para clausulas WHERE (CWE-943).
_FILTER_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,64}$")
# Caracteres prohibidos en valores string: cierran/escapan el literal SQL.
_UNSAFE_FILTER_CHARS = ("'", '"', "\\")


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

    @staticmethod
    def _is_safe_filter_value(value: Any) -> bool:
        """Indica si un valor de filtro es seguro para interpolar en SQL.

        WHAT: comprueba que ``value`` sea escalar y que, si es string, no
        contenga comillas ni backslash.
        WHY: evita inyeccion de predicados en los filtros de LanceDB (CWE-943).
        WHERE: ``_LanceDBBackendMixin._update_records_lancedb``.

        Args:
            value: Valor de filtro a inspeccionar.

        Returns:
            True si el valor puede interpolarse sin riesgo.
        """
        if isinstance(value, str):
            return not any(ch in value for ch in _UNSAFE_FILTER_CHARS)
        return isinstance(value, (bool, int, float)) or value is None

    @classmethod
    def _safe_where_comparison(cls, key: Any, value: Any) -> str:
        """Construye una comparacion ``clave = valor`` segura para LanceDB.

        WHAT: valida ``key`` contra una allowlist y rechaza valores string
        con comillas o backslash antes de interpolarlos en una clausula WHERE.
        WHY: sin validacion, un filtro como ``{"x": "a' OR '1'='1"}`` inyecta
        predicados y altera el conjunto de registros afectados (CWE-943).
        WHERE: ``_LanceDBBackendMixin._update_records_lancedb``.

        Args:
            key: Nombre de campo; debe cumplir ``^[A-Za-z0-9_]{1,64}$``.
            value: Valor escalar; los strings deben carecer de ``'``/``"``/``\\``.

        Returns:
            Fragmento de comparacion listo para unir con ``AND``.

        Raises:
            ValueError: Si la clave o el valor no son seguros.
        """
        if not isinstance(key, str) or not _FILTER_KEY_PATTERN.match(key):
            raise ValueError(
                "Filtro LanceDB invalido (key); "
                f"WHAT=clave rechazada {key!r}; "
                "WHY=previene inyeccion de filtros (CWE-943); "
                "WHERE=_update_records_lancedb; "
                "EXPECTED=^[A-Za-z0-9_]{1,64}$"
            )
        if isinstance(value, str):
            if not cls._is_safe_filter_value(value):
                raise ValueError(
                    "Filtro LanceDB invalido (value); "
                    f"WHAT=string rechazado {value!r}; "
                    "WHY=previene inyeccion de filtros (CWE-943); "
                    "WHERE=_update_records_lancedb; "
                    "EXPECTED=sin ' \" \\\\"
                )
            return f"{key} = '{value}'"
        if not cls._is_safe_filter_value(value):
            raise ValueError(
                "Filtro LanceDB invalido (value); "
                f"WHAT=tipo no soportado {type(value).__name__}; "
                "WHY=solo se permiten str/int/float/bool/None; "
                "WHERE=_update_records_lancedb"
            )
        return f"{key} = {value}"

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

        # Construir clausula WHERE desde los filtros (clave/valor validados)
        conditions = [
            self._safe_where_comparison(k, v) for k, v in filters.items()
        ]
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
            # El id leido de la tabla tambien se interpola: validarlo evita
            # que un id manipulado inyecte predicates en el UPDATE (CWE-943).
            if not self._is_safe_filter_value(record_id):
                logger.warning(
                    "update_records LanceDB: id no seguro omitido en '%s' "
                    "(WHAT=id con comillas/backslash WHY=anti-inyeccion "
                    "WHERE=_update_records_lancedb)",
                    collection,
                )
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
