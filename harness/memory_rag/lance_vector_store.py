"""
Unified vector store interface for RAG and metadata search using LanceDB.
Supports three core collections: tasks_board, rag_chunks, asi_cognition_store.
Graceful fallback to in-memory dict + numpy when LanceDB is unavailable.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LANCEDB_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "db",
    "lancedb_store",
)

DEFAULT_COLLECTIONS = {
    "tasks_board": {
        "description": "Task assignments, statuses, and agent routing records",
        "schema": {
            "id": "string",
            "agent": "string",
            "task": "string",
            "status": "string",
            "vector": "list<float>",
            "metadata": "dict",
            "created_at": "string",
        },
    },
    "rag_chunks": {
        "description": "Knowledge chunks retrieved for RAG-enhanced inference",
        "schema": {
            "id": "string",
            "domain": "string",
            "chunk": "string",
            "vector": "list<float>",
            "metadata": "dict",
            "created_at": "string",
        },
    },
    "asi_cognition_store": {
        "description": "Lessons, insights, and cognition artifacts from evolve loops",
        "schema": {
            "id": "string",
            "title": "string",
            "content": "string",
            "domain": "string",
            "tags": "list<string>",
            "metrics": "dict",
            "vector": "list<float>",
            "created_at": "string",
        },
    },
}


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
    vector: Optional[np.ndarray]
    metadata: Dict[str, Any]
    created_at: str


@dataclass
class _Collection:
    """An in-memory collection mirroring a LanceDB table."""
    name: str
    schema_def: Dict[str, str]
    items: Dict[str, _StoredItem] = field(default_factory=dict)
    last_updated: str = ""


# ---------------------------------------------------------------------------
# LanceVectorStore
# ---------------------------------------------------------------------------


class LanceVectorStore:
    """
    Unified vector store that wraps LanceDB with an in-memory fallback.

    Collections are auto-created on first use.  When LanceDB is not installed
    or the database path is unavailable all operations degrade to pure-numpy
    dict-backed stores, keeping the same public API.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or LANCEDB_ROOT
        self._lancedb_available = False
        self._db: Any = None  # LanceDB connection or None
        self._mem_collections: Dict[str, _Collection] = {}
        self._embedding_dim: int = 384  # default; adjusted on first insert

        self._init_storage()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_storage(self) -> None:
        """Attempt to open LanceDB; fall back to in-memory if it fails."""
        # Try LanceDB first
        lancedb = self._try_import_lancedb()
        if lancedb is not None:
            try:
                os.makedirs(self.db_path, exist_ok=True)
                self._db = lancedb.connect(self.db_path)
                self._lancedb_available = True
                logger.info("LanceVectorStore connected to %s", self.db_path)
                self._ensure_lancedb_collections()
                return
            except Exception as exc:
                logger.warning(
                    "LanceDB connect failed (%s); using in-memory fallback.", exc
                )

        # Fallback
        logger.info("LanceVectorStore using in-memory dict fallback.")
        self._lancedb_available = False
        self._db = None
        for name, info in DEFAULT_COLLECTIONS.items():
            self._mem_collections[name] = _Collection(
                name=name,
                schema_def=info["schema"],
                last_updated=datetime.now(timezone.utc).isoformat(),
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
        """Create default tables in LanceDB if they don't exist."""
        if not self._lancedb_available or self._db is None:
            return
        for name in DEFAULT_COLLECTIONS:
            try:
                self._db.create_table(name, data=[], mode="exist_ok")
            except Exception:
                # Table may already exist with data; that is fine
                pass

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def create_collection(
        self, name: str, schema: Optional[Dict[str, str]] = None
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
                last_updated=datetime.now(timezone.utc).isoformat(),
            )

    def list_collections(self) -> List[str]:
        """Return list of available collection names."""
        if self._lancedb_available and self._db is not None:
            return list(self._db.table_names())
        return list(self._mem_collections.keys())

    # ------------------------------------------------------------------
    # Insert
    # ------------------------------------------------------------------

    def insert(
        self,
        collection: str,
        vectors: np.ndarray,
        metadata: List[Dict[str, Any]],
    ) -> List[str]:
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

        ids: List[str] = []
        now = datetime.now(timezone.utc).isoformat()

        if self._lancedb_available and self._db is not None:
            ids = self._insert_lancedb(collection, vectors, metadata, now)
        else:
            ids = self._insert_memory(collection, vectors, metadata, now)

        return ids

    def _insert_lancedb(
        self,
        collection: str,
        vectors: np.ndarray,
        metadata: List[Dict[str, Any]],
        now: str,
    ) -> List[str]:
        tbl = self._db.open_table(collection)  # type: ignore[union-attr]
        rows: List[Dict[str, Any]] = []
        ids: List[str] = []
        for i in range(vectors.shape[0]):
            rid = str(uuid.uuid4())
            ids.append(rid)
            rows.append(
                {
                    "id": rid,
                    "vector": vectors[i].tolist(),
                    "metadata": json.dumps(metadata[i]),
                    "created_at": now,
                    **{k: v for k, v in metadata[i].items() if k != "metadata"},
                }
            )
        tbl.add(rows)
        return ids

    def _insert_memory(
        self,
        collection: str,
        vectors: np.ndarray,
        metadata: List[Dict[str, Any]],
        now: str,
    ) -> List[str]:
        col = self._get_or_create_mem_collection(collection)
        ids: List[str] = []
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

        if vectors.shape[1] > self._embedding_dim:
            self._embedding_dim = vectors.shape[1]

        return ids

    def _get_or_create_mem_collection(self, name: str) -> _Collection:
        """Ensure in-memory collection exists; create on demand."""
        if name not in self._mem_collections:
            self._mem_collections[name] = _Collection(
                name=name,
                schema_def={},
                last_updated=datetime.now(timezone.utc).isoformat(),
            )
        return self._mem_collections[name]

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        collection: str,
        query_vector: np.ndarray,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
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
        filters: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        try:
            tbl = self._db.open_table(collection)
        except Exception as exc:
            raise CollectionNotFoundError(
                f"Collection '{collection}' not found in LanceDB: {exc}"
            ) from exc

        query_list = query_vector.tolist()
        results = tbl.search(query_list).limit(top_k).to_list()

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

        out: List[Dict[str, Any]] = []
        for r in results:
            meta = r.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    meta = {}
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
        filters: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
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
            filtered: List[_StoredItem] = []
            for item in candidates:
                match = all(
                    item.metadata.get(k) == v for k, v in filters.items()
                )
                if match:
                    filtered.append(item)
            candidates = filtered

        if not candidates:
            return []

        # Compute cosine similarity
        q_norm = query_vector / (np.linalg.norm(query_vector) + 1e-12)

        vectors = np.array(
            [c.vector for c in candidates if c.vector is not None]
        )
        if vectors.size == 0:
            return []

        # (n, dim) -> (n,) dot product
        sims = vectors @ q_norm
        top_indices = np.argsort(sims)[-top_k:][::-1]

        results: List[Dict[str, Any]] = []
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
    ) -> List[Dict[str, Any]]:
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

        def _keyword_score(item: Dict[str, Any]) -> float:
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

    def get_collection_stats(self, name: str) -> Dict[str, Any]:
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

    def _stats_lancedb(self, name: str) -> Dict[str, Any]:
        try:
            tbl = self._db.open_table(name)
        except Exception as exc:
            raise CollectionNotFoundError(
                f"Collection '{name}' not found: {exc}"
            ) from exc
        data = tbl.to_list()
        schema = DEFAULT_COLLECTIONS.get(name, {}).get("schema", {})
        last_up = ""
        if data:
            last_up = data[-1].get("created_at", "")
        return {
            "name": name,
            "item_count": len(data),
            "schema": schema,
            "last_updated": last_up,
        }

    def _stats_memory(self, name: str) -> Dict[str, Any]:
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
            for name in self._db.table_names():
                try:
                    self._db.drop_table(name)
                except Exception:
                    pass
        self._mem_collections.clear()
        for name, info in DEFAULT_COLLECTIONS.items():
            self._mem_collections[name] = _Collection(
                name=name,
                schema_def=info["schema"],
                last_updated=datetime.now(timezone.utc).isoformat(),
            )
