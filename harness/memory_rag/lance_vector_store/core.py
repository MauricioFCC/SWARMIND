"""Clase principal ``LanceVectorStore``.

Extraido mecanicamente de ``lance_vector_store.py`` (regla AGR < 500 lineas).
La clase conserva la misma API publica y privada; los metodos privados de
backend viven en los mixins de ``backends.py``. Sin cambios de logica.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

# Import del paquete para resolver get_memory_config en runtime: replica el
# global lookup del modulo plano original, de modo que parches de tests como
# ``patch("harness.memory_rag.lance_vector_store.get_memory_config")``
# sigan afectando a __init__() y from_config().
import harness.memory_rag.lance_vector_store as _lance_vector_store

from ..lance_schemas import DEFAULT_COLLECTIONS
from ..memory_config import MemoryConfig
from .backends import _LanceDBBackendMixin, _MemoryBackendMixin
from .constants import LANCEDB_ROOT
from .exceptions import VectorStoreError
from .models import _Collection

logger = logging.getLogger("harness.memory_rag.lance_vector_store")


class LanceVectorStore(_LanceDBBackendMixin, _MemoryBackendMixin):
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
                    se toman del config si no se especifican explicitamente.
        """
        if config:
            self.db_path = db_path or config.lancedb_path
            if not allow_fallback:
                allow_fallback = config.allow_fallback
        else:
            # Default: memoria central (MemoryConfig resuelve env > .swarmind_config
            # > legacy). Evita DBs paralelas en rutas relativas al codigo.
            self.db_path = (
                db_path
                or _lance_vector_store.get_memory_config().lancedb_path
                or LANCEDB_ROOT
            )
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
        cfg = config or _lance_vector_store.get_memory_config()
        return cls(
            db_path=cfg.lancedb_path,
            allow_fallback=cfg.allow_fallback,
            config=cfg,
        )
