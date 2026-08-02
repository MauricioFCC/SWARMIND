"""
Unified vector store interface for RAG and metadata search using LanceDB.
LanceDB es OBLIGATORIO. Si no esta disponible, se lanza un error claro.
El fallback in-memory solo se activa con allow_fallback=True (emergencias/test).

REFACTOR: Usa _infer_schema_recursive() desde lance_migration.py para
inferir schemas recursivamente, eliminando ~100 lÃ­neas de if/elif anidados
en _sample_row_for_collection().
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .lance_migration import generate_sample_row, serialize_for_schema
from .lance_schemas import DEFAULT_COLLECTIONS
from .memory_config import MemoryConfig, get_memory_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants & Schemas (extracted to lance_schemas.py for file size)
# ---------------------------------------------------------------------------

LANCEDB_ROOT = str(
    Path(__file__).resolve().parent.parent / "db" / "lancedb"
)

# Collection name constants for external consumption
COLLECTION_PROCEDURAL_SKILLS = "procedural_skills"
COLLECTION_PROMPT_EVOLUTION_LOG = "prompt_evolution_log"
COLLECTION_SCHEDULER_LOG = "scheduler_log"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CollectionNotFoundError(Exception):
    """Raised when an operation targets a non-existent collection."""


class VectorStoreError(Exception):
    """Base exception for vector store operations."""


# ---------------------------------------------------------------------------
# In-memory fallback types
# ---------------------------------------------------------------------------


@dataclass
class _StoredItem:
    """A single item held in the in-memory fallback store."""
    id: str
    vector: np.ndarray | None
    metadata: dict[str, Any]
    created_at: str


@dataclass
class _Collection:
    """An in-memory collection mirroring a LanceDB table."""
    name: str
    schema_def: dict[str, str]
    items: dict[str, _StoredItem] = field(default_factory=dict)
    last_updated: str = ""


# ---------------------------------------------------------------------------
# LanceVectorStore
# ---------------------------------------------------------------------------


class LanceVectorStore:
    """
    Unified vector store that wraps LanceDB.

    LanceDB es OBLIGATORIO. Si no esta instalado, se lanza ImportError.
    El fallback in-memory (dict + numpy) solo se activa si allow_fallback=True,
    tipicamente para entornos de test o emergencias controladas.

    Collections are auto-created on first use.
    """

    def __init__(
        self,
        db_path: str | None = None,
        allow_fallback: bool = False,
        config: MemoryConfig | None = None,
    ) -> None:
        """Inicializa el vector store con conexion a LanceDB.

        Args:
            db_path: Ruta a la base LanceDB. Si no se especifica, se usa
                     la ruta por defecto o la del MemoryConfig.
            allow_fallback: Permitir fallback a memoria en RAM si LanceDB falla.
            config: MemoryConfig opcional. Si se provee, db_path y allow_fallback
                    se toman del config si no se especifican explÃ­citamente.
        """
        if config:
            self.db_path = db_path or config.lancedb_path
            if not allow_fallback:
                allow_fallback = config.allow_fallback
        else:
            self.db_path = db_path or LANCEDB_ROOT
        self._lancedb_available = False
        self._db: Any = None  # LanceDB connection or None
        self._mem_collections: dict[str, _Collection] = {}
        self._embedding_dim: int = 384  # default; adjusted on first insert
        self._allow_fallback = allow_fallback

        self._init_storage()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_storage(self) -> None:
        """Attempt to open LanceDB; fail with clear error if unavailable."""
        # Try LanceDB first
        lancedb = self._try_import_lancedb()
        if lancedb is not None:
            try:
                Path(self.db_path).mkdir(parents=True, exist_ok=True)
                self._db = lancedb.connect(self.db_path)
                self._lancedb_available = True
                logger.info("LanceVectorStore connected to %s", self.db_path)
                self._ensure_lancedb_collections()
                return
            except Exception as exc:
                logger.warning(
                    "LanceDB connect failed: %s", exc,
                )
                if self._allow_fallback:
                    logger.warning(
                        "Usando fallback in-memory (allow_fallback=True). "
                        "NO RECOMENDADO para produccion."
                    )
                else:
                    raise RuntimeError(
                        f"LanceDB no pudo conectarse en {self.db_path}: {exc}\n"
                        "Verifica que LanceDB este instalado y la ruta sea valida.\n"
                        "  pip install lancedb\n"
                        "  python harness/scripts/init.py"
                    ) from exc

        else:
            # lancedb import failed
            msg = (
                "LanceDB no esta instalado. Es OBLIGATORIO para el funcionamiento.\n"
                "  pip install lancedb\n"
                "  python harness/scripts/init.py"
            )
            if self._allow_fallback:
                logger.warning(
                    "LanceDB no instalado. Usando fallback in-memory "
                    "(allow_fallback=True). NO RECOMENDADO para produccion."
                )
            else:
                raise ImportError(msg)

        # Fallback in-memory (solo si allow_fallback=True)
        logger.warning(
            "LanceVectorStore usando fallback in-memory (dict + numpy). "
            "Rendimiento limitado y sin persistencia."
        )
        self._lancedb_available = False
        self._db = None
        for name, info in DEFAULT_COLLECTIONS.items():
            self._mem_collections[name] = _Collection(
                name=name,
                schema_def=info["schema"],
                last_updated=datetime.now(UTC).isoformat(),
            )

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

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def create_collection(
        self, name: str, schema: dict[str, str] | None = None
    ) -> None:
        """
        Create a new collection.

        Args:
            name: Collection name.
            schema: Optional dict of field_name -> type_string.
        """
        if self._lancedb_available and self._db is not None:
            try:
                self._db.create_table(name, data=[], mode="overwrite")
                logger.info("Created LanceDB table '%s'", name)
            except Exception as exc:
                raise VectorStoreError(
                    f"Failed to create LanceDB table '{name}': {exc}"
                ) from exc
        else:
            if name in self._mem_collections:
                logger.warning("Collection '%s' already exists; overwriting.", name)
            self._mem_collections[name] = _Collection(
                name=name,
                schema_def=schema or {},
                last_updated=datetime.now(UTC).isoformat(),
            )

    def list_collections(self) -> list[str]:
        """Return list of available collection names."""
        if self._lancedb_available and self._db is not None:
            return list(self._db.list_tables().tables)
        return list(self._mem_collections.keys())

    # ------------------------------------------------------------------
    # Insert
    # ------------------------------------------------------------------

    def insert(
        self,
        collection: str,
        vectors: np.ndarray,
        metadata: list[dict[str, Any]],
    ) -> list[str]:
        """
        Insert vectors with associated metadata into a collection.

        Args:
            collection: Target collection name.
            vectors: 2-D numpy array of shape (n_items, dim).
            metadata: List of dicts, one per vector.

        Returns:
            List of inserted record IDs.
        """
        n = vectors.shape[0]
        if n == 0:
            return []

        ids: list[str] = []
        now = datetime.now(UTC).isoformat()

        if self._lancedb_available and self._db is not None:
            ids = self._insert_lancedb(collection, vectors, metadata, now)
        else:
            ids = self._insert_memory(collection, vectors, metadata, now)

        return ids

    def _insert_lancedb(
        self,
        collection: str,
        vectors: np.ndarray,
        metadata: list[dict[str, Any]],
        now: str,
    ) -> list[str]:
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

    def _insert_memory(
        self,
        collection: str,
        vectors: np.ndarray,
        metadata: list[dict[str, Any]],
        now: str,
    ) -> list[str]:
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

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_records(
        self,
        collection: str,
        filters: dict[str, Any],
        updates: dict[str, Any],
    ) -> int:
        """
        Actualiza registros que coinciden con los filtros en una coleccion.

        Args:
            collection: Nombre de la coleccion.
            filters: Dict de campo -> valor para seleccionar registros.
            updates: Dict de campo -> valor con los cambios a aplicar.

        Returns:
            Numero de registros actualizados.
        """
        if self._lancedb_available and self._db is not None:
            return self._update_records_lancedb(collection, filters, updates)
        return self._update_records_memory(collection, filters, updates)

    def _update_records_lancedb(
        self,
        collection: str,
        filters: dict[str, Any],
        updates: dict[str, Any],
    ) -> int:
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

    def _update_records_memory(
        self,
        collection: str,
        filters: dict[str, Any],
        updates: dict[str, Any],
    ) -> int:
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

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        collection: str,
        query_vector: np.ndarray,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Vector similarity search with optional metadata filtering.

        Args:
            collection: Collection name.
            query_vector: 1-D query embedding.
            top_k: Number of results to return.
            filters: Optional dict of field -> value for pre-filtering.

        Returns:
            List of result dicts with keys: id, score, metadata, created_at.
        """
        if self._lancedb_available and self._db is not None:
            return self._search_lancedb(collection, query_vector, top_k, filters)

        return self._search_memory(collection, query_vector, top_k, filters)

    def _search_lancedb(
        self,
        collection: str,
        query_vector: np.ndarray,
        top_k: int,
        filters: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
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

    def _search_memory(
        self,
        collection: str,
        query_vector: np.ndarray,
        top_k: int,
        filters: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
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

    # ------------------------------------------------------------------
    # Hybrid search
    # ------------------------------------------------------------------

    def hybrid_search(
        self,
        collection: str,
        query_vector: np.ndarray,
        keyword_filter: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Hybrid search combining vector similarity with keyword filtering.

        The keyword filter is matched against the 'domain' and 'tags' fields
        of stored metadata.

        Args:
            collection: Collection name.
            query_vector: 1-D query embedding.
            keyword_filter: Keyword string to match against metadata fields.
            top_k: Number of results to return.

        Returns:
            List of result dicts.
        """
        # Start with vector search, then re-rank by keyword presence
        vector_results = self.search(collection, query_vector, top_k * 3)

        kw_lower = keyword_filter.lower()

        def _keyword_score(item: dict[str, Any]) -> float:
            meta = item.get("metadata", {})
            fields_to_check = [
                str(meta.get("domain", "")),
                str(meta.get("title", "")),
                str(meta.get("chunk", "")),
                " ".join(meta.get("tags", [])),
            ]
            text = " ".join(fields_to_check).lower()
            return 1.0 if kw_lower in text else 0.0

        for item in vector_results:
            item["_keyword_bonus"] = _keyword_score(item)

        # Combined score: 0.7 * vector_score + 0.3 * keyword_bonus
        for item in vector_results:
            score = item.get("score", 0.0)
            bonus = item.get("_keyword_bonus", 0.0)
            item["combined_score"] = 0.7 * score + 0.3 * bonus

        reranked = sorted(
            vector_results,
            key=lambda x: x.get("combined_score", 0.0),
            reverse=True,
        )

        # Strip internal keys before returning
        for item in reranked:
            item.pop("_keyword_bonus", None)

        return reranked[:top_k]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_collection_stats(self, name: str) -> dict[str, Any]:
        """
        Return collection metadata: item_count, schema, last_updated.

        Args:
            name: Collection name.

        Returns:
            Dict with keys: name, item_count, schema, last_updated.
        """
        if self._lancedb_available and self._db is not None:
            return self._stats_lancedb(name)

        return self._stats_memory(name)

    def _stats_lancedb(self, name: str) -> dict[str, Any]:
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
                # Obtener solo la Ãºltima fila para timestamp
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

    def _stats_memory(self, name: str) -> dict[str, Any]:
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

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def delete_collection(self, name: str) -> None:
        """Remove an entire collection."""
        if self._lancedb_available and self._db is not None:
            try:
                self._db.drop_table(name)
            except Exception as exc:
                raise VectorStoreError(
                    f"Failed to drop LanceDB table '{name}': {exc}"
                ) from exc
        else:
            if name in self._mem_collections:
                del self._mem_collections[name]

    def clear(self) -> None:
        """Remove all collections and reset to defaults."""
        if self._lancedb_available and self._db is not None:
            for name in self._db.list_tables().tables:
                try:
                    self._db.drop_table(name)
                except Exception as _exc:  # noqa: BLE001
                    logger.warning("lance_vector_store: %s", _exc)
        self._mem_collections.clear()
        for name, info in DEFAULT_COLLECTIONS.items():
            self._mem_collections[name] = _Collection(
                name=name,
                schema_def=info["schema"],
                last_updated=datetime.now(UTC).isoformat(),
            )

    @classmethod
    def from_config(cls, config: MemoryConfig | None = None) -> LanceVectorStore:
        """Crea un LanceVectorStore desde un MemoryConfig.

        Args:
            config: MemoryConfig. Si es None, usa get_memory_config().

        Returns:
            LanceVectorStore configurado.
        """
        cfg = config or get_memory_config()
        return cls(
            db_path=cfg.lancedb_path,
            allow_fallback=cfg.allow_fallback,
            config=cfg,
        )
