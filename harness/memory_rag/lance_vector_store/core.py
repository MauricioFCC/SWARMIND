"""Clase principal ``LanceVectorStore``.

Extraido mecanicamente de ``lance_vector_store.py`` (regla AGR < 500 lineas).
La clase conserva la misma API publica y privada; los metodos privados de
backend viven en los mixins de ``backends.py``.

Seleccion de backend (Clean Architecture, ADR-0098): la clase es el adaptador
LanceDB/in-memory. Si el backend efectivo es ``ruscadb``, ``__new__`` devuelve
un :class:`RuscaDBStore` real en lugar de un ``LanceVectorStore`` parcheado con
``setattr``; asi el tipo del objeto refleja la infraestructura que lo respalda
y no hay metodos huerfanos que fallaran sobre ``self._db = None``.
"""
from __future__ import annotations

import logging
import os
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
from ..memory_config import MemoryBackend, MemoryConfig
from .backends import _LanceDBBackendMixin
from .constants import LANCEDB_ROOT
from .exceptions import VectorStoreError
from .lifecycle import _LifecycleMixin
from .models import _Collection

logger = logging.getLogger("harness.memory_rag.lance_vector_store")

#: Backend por defecto (RuscaDB es la persistencia unica desde el ciclo 11.42).
DEFAULT_BACKEND = "ruscadb"


def _resolve_backend(backend: str | None, config: Any = None) -> str:
    """Resuelve el backend efectivo de memoria.

    Precedencia: argumento explicito > ``VECTOR_BACKEND`` > config > default.

    Args:
        backend: Backend pedido por el llamador.
        config: MemoryConfig opcional con ``vector_backend`` o ``backend``.

    Returns:
        Nombre del backend en minusculas (``ruscadb``/``lancedb``/``memory``).
    """
    if backend is None:
        backend = os.environ.get("VECTOR_BACKEND")
    if backend is None and config is not None:
        candidate = getattr(config, "vector_backend", None)
        if candidate is None:
            candidate = getattr(config, "backend", None)
        backend = getattr(candidate, "value", candidate)
    return str(backend or DEFAULT_BACKEND).lower()


class LanceVectorStore(_LanceDBBackendMixin, _LifecycleMixin):
    """
    Unified vector store that wraps LanceDB.

    LanceDB es OBLIGATORIO. Si no esta instalado, se lanza ImportError.
    El fallback in-memory (dict + numpy) solo se activa si allow_fallback=True,
    tipicamente para entornos de test o emergencias controladas.

    Collections are auto-created on first use.
    """

    def __new__(
        cls,
        db_path: str | None = None,
        allow_fallback: bool = False,
        config: MemoryConfig | None = None,
        backend: str | None = None,
    ) -> Any:
        """Devuelve el adaptador que corresponde al backend efectivo.

        Con backend ``ruscadb`` (default) se construye y devuelve un
        :class:`RuscaDBStore`; Python no invoca ``__init__`` de esta clase
        porque el objeto devuelto no es una instancia de ``cls``. Si RuscaDB
        no esta disponible se degrada a LanceDB/in-memory con warning.

        Args:
            db_path: Ruta de la base.
            allow_fallback: Habilita fallback in-memory (LanceDB).
            config: MemoryConfig opcional.
            backend: Backend pedido.

        Returns:
            Instancia de RuscaDBStore o de LanceVectorStore.

        Raises:
            No propaga errores de RuscaDB: los convierte en fallback a LanceDB.
        """
        if cls is not LanceVectorStore:
            return super().__new__(cls)
        if _resolve_backend(backend, config) != "ruscadb":
            return super().__new__(cls)
        try:
            from ..ruscadb import load_library

            load_library()
        except (ImportError, OSError) as exc:
            # El artefacto dinamico no esta en esta plataforma/instalacion:
            # degradar es el unico camino (no hay motor que abrir).
            logger.warning(
                "RuscaDB no instalado (%s); backend efectivo = lancedb", exc
            )
            return super().__new__(cls)
        try:
            from ..ruscadb_store import RuscaDBStore

            return RuscaDBStore(
                db_path=db_path, allow_fallback=allow_fallback, config=config
            )
        except (ImportError, OSError, RuntimeError) as exc:
            if allow_fallback:
                logger.warning(
                    "RuscaDB fallo (%s) con allow_fallback=True; backend = lancedb",
                    exc,
                )
                return super().__new__(cls)
            # Fail-fast: desviar escrituras a otra base produce memoria
            # partida y perdida silenciosa de persistencia (DB bloqueada,
            # corrupta o lock de otro proceso).
            raise RuntimeError(
                "LanceVectorStore | WHAT=adaptador_ruscadb_no_disponible | "
                f"WHY={exc} | WHERE=LanceVectorStore.__new__ | "
                "sugerencia: allow_fallback=True o backend='lancedb'"
            ) from exc

    def __init__(
        self,
        db_path: str | None = None,
        allow_fallback: bool = False,
        config: MemoryConfig | None = None,
        backend: str | None = None,
    ) -> None:
        """Inicializa el vector store con conexion a LanceDB.

        Args:
            db_path: Ruta a la base LanceDB. Si no se especifica, se usa
                     la ruta por defecto o la del MemoryConfig.
            allow_fallback: Permitir fallback a memoria en RAM si LanceDB falla.
            config: MemoryConfig opcional. Si se provee, db_path y allow_fallback
                    se toman del config si no se especifican explicitamente.
            backend: Backend solicitado; ``ruscadb`` solo llega aqui si
                    ``__new__`` no pudo construir el adaptador RuscaDB.
        """
        resolved = _resolve_backend(backend, config)
        if resolved == "ruscadb":
            # __new__ ya habria devuelto el RuscaDBStore; llegar aqui implica
            # que el motor no esta disponible y se degrada a LanceDB.
            logger.info("Fallback de backend: ruscadb no disponible, se usa lancedb")
            resolved = "lancedb"
        if resolved == "memory":
            # El backend memory ES el fallback in-memory: no tiene sentido
            # exigir lancedb para usarlo.
            allow_fallback = True
        self._backend = resolved
        self._rusca = None
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
            vectors: Matriz (n_items, dim) o vector unico (lista o ndarray).
            metadata: List of dicts, one per vector.

        Returns:
            List of inserted record IDs.
        """
        array = self._normalized_matrix(vectors)
        if array is None:
            return []

        ids: list[str] = []
        now = datetime.now(UTC).isoformat()

        if self._lancedb_available and self._db is not None:
            ids = self._insert_lancedb(collection, array, metadata, now)
        else:
            ids = self._insert_memory(collection, array, metadata, now)

        return ids

    @staticmethod
    def _normalized_matrix(vectors: np.ndarray) -> np.ndarray | None:
        """Normaliza la entrada a matriz 2-D float32 (None si esta vacia)."""
        array = np.asarray(vectors, dtype=np.float32)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        return None if array.shape[0] == 0 else array

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
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Vector similarity search with optional metadata filtering.

        Args:
            collection: Collection name.
            query_vector: 1-D query embedding.
            top_k: Number of results to return.
            filters: Optional dict of field -> value for pre-filtering.
            **kwargs: Opciones de gobernanza aceptadas por el puerto
                (``allow_quarantined``/``min_trust``/``half_life_days``);
                LanceDB no las aplica (no hay trust tagging nativo).

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
        query_text: str = "",
        top_k: int = 5,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Hybrid search combining vector similarity with keyword filtering.

        The keyword filter is matched against the 'domain' and 'tags' fields
        of stored metadata.

        Args:
            collection: Collection name.
            query_vector: 1-D query embedding.
            query_text: Keyword string to match against metadata fields.
            top_k: Number of results to return.
            **kwargs: ``keyword_filter`` se acepta como alias historico.

        Returns:
            List of result dicts.
        """
        alias = kwargs.pop("keyword_filter", None)
        if alias is not None:
            query_text = str(alias)
        # Start with vector search, then re-rank by keyword presence
        vector_results = self.search(collection, query_vector, top_k * 3)

        kw_lower = query_text.lower()

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

    @classmethod
    def from_config(cls, config: MemoryConfig | None = None) -> LanceVectorStore:
        """Crea un LanceVectorStore desde un MemoryConfig.

        Args:
            config: MemoryConfig. Si es None, usa get_memory_config().

        Returns:
            LanceVectorStore configurado.
        """
        cfg = config or _lance_vector_store.get_memory_config()
        db_path = cfg.ruscadb_path if cfg.backend == MemoryBackend.RUSCADB else cfg.lancedb_path
        return cls(
            db_path=db_path,
            allow_fallback=cfg.allow_fallback,
            config=cfg,
            backend=cfg.backend.value if hasattr(cfg.backend, "value") else str(cfg.backend),
        )
