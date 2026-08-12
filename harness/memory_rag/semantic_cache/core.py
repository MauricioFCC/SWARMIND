"""Clase principal ``SemanticCache``.

Extraido mecanicamente de ``semantic_cache.py`` (regla AGR < 500 lineas).
La clase conserva la misma API publica; los helpers privados viven en el
mixin ``_SemanticCacheOpsMixin`` de ``ops.py``. Sin cambios de logica.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import numpy as np

from ..lance_vector_store import LanceVectorStore
from .constants import (
    COLLECTION_SEMANTIC_CACHE,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_TTL_SECONDS,
)
from .models import CacheEntry
from .ops import _SemanticCacheOpsMixin

logger = logging.getLogger("harness.memory_rag.semantic_cache")


class SemanticCache(_SemanticCacheOpsMixin):
    """
    Cache semantico de respuestas LLM usando LanceDB.

    Uso tipico::

        store = LanceVectorStore()
        cache = SemanticCache(store, threshold=0.92)

        # Antes de llamar al LLM:
        cached = cache.get(prompt, agent_role)
        if cached:
            return cached  # LLM call evitada

        # Despues de obtener respuesta del LLM:
        cache.set(prompt, response, agent_role)
    """

    def __init__(
        self,
        vector_store: LanceVectorStore | None = None,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        default_ttl: int = DEFAULT_TTL_SECONDS,
        embedding_fn: Callable[[str], np.ndarray] | None = None,
        auto_create_collection: bool = True,
    ) -> None:
        """
        Args:
            vector_store: Instancia de LanceVectorStore. Si None, se crea una.
            threshold: Umbral de similitud para considerar cache hit (0.0 - 1.0).
            default_ttl: TTL por defecto en segundos para nuevas entradas.
            embedding_fn: Funcion para convertir texto a vector. Si None, se usa
                         embedding de caracteres (deterministico, no requiere modelo).
            auto_create_collection: Si True, crea la coleccion si no existe.
        """
        self._store = vector_store or LanceVectorStore()
        self._threshold = threshold
        self._default_ttl = default_ttl
        self._embedding_fn = embedding_fn or self._default_embedding
        self._stats: dict[str, Any] = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "expired": 0,
            "total_requests": 0,
        }

        if auto_create_collection:
            self._ensure_collection()

        logger.info(
            "SemanticCache initialized (threshold=%.2f, ttl=%ds, collection='%s')",
            threshold, default_ttl, COLLECTION_SEMANTIC_CACHE,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self,
        prompt: str,
        agent_role: str = "*",
        threshold: float | None = None,
    ) -> str | None:
        """
        Buscar respuesta cacheada para un prompt.

        Args:
            prompt: El prompt del agente.
            agent_role: Rol del agente (para filtrado opcional).
            threshold: Umbral para esta busqueda (usa el default si None).

        Returns:
            La respuesta cacheada o None si no hay match.
        """
        self._stats["total_requests"] += 1
        effective_threshold = threshold if threshold is not None else self._threshold

        # 1. Hash exacto (cache hit perfecto, mas rapido)
        exact_hash = self._hash_prompt(prompt)
        exact_result = self._search_exact(exact_hash, agent_role)
        if exact_result is not None:
            response, entry = exact_result
            if entry.is_expired():
                self._stats["expired"] += 1
                self._delete_entry(entry.prompt_hash)
                logger.debug("Cache entry expired (hash=%s)", exact_hash[:8])
            else:
                self._stats["hits"] += 1
                self._update_hit_count(entry)
                logger.debug(
                    "SemanticCache EXACT HIT (hash=%s, agent=%s)",
                    exact_hash[:8], agent_role,
                )
                return response

        # 2. Busqueda por similitud semantica
        query_vec = self._embedding_fn(prompt)
        try:
            results = self._store.search(
                COLLECTION_SEMANTIC_CACHE,
                query_vec,
                top_k=10,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("SemanticCache search failed: %s", exc)
            self._stats["misses"] += 1
            return None

        # 3. Evaluar resultados (con post-filter por agent_role)
        for result in results:
            raw_score = result.get("score", 0.0)
            score = self._normalize_similarity(raw_score)
            if score < effective_threshold:
                continue

            meta = result.get("metadata", {})
            if not isinstance(meta, dict):
                continue

            # Post-filter: agent_role
            result_role = meta.get("agent_role", "*")
            if agent_role != "*" and result_role not in (agent_role, "*"):
                continue

            response = meta.get("response", "")
            if not response:
                continue

            # Verificar expiracion
            created_at = meta.get("created_at", "")
            ttl = meta.get("ttl_seconds", self._default_ttl)
            if self._is_expired(created_at, ttl):
                self._stats["expired"] += 1
                prompt_hash = meta.get("prompt_hash", "")
                if prompt_hash:
                    self._delete_entry(prompt_hash)
                continue

            # Cache hit!
            self._stats["hits"] += 1
            prompt_hash = meta.get("prompt_hash", "")
            if prompt_hash:
                self._update_hit_count(
                    CacheEntry(
                        prompt_hash=prompt_hash,
                        prompt_text=prompt,
                        response=response,
                        agent_role=agent_role,
                    )
                )

            logger.debug(
                "SemanticCache SIMILARITY HIT (score=%.4f, agent=%s)",
                score, agent_role,
            )
            return response

        self._stats["misses"] += 1
        return None

    def set(
        self,
        prompt: str,
        response: str,
        agent_role: str = "*",
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Almacenar respuesta en cache.

        Si ya existe una entrada con el mismo ``prompt_hash`` cuyo campo
        ``response`` contiene ``[PENDING]``, se elimina antes de insertar
        la nueva entrada para evitar duplicados.

        Args:
            prompt: El prompt original.
            response: La respuesta del LLM.
            agent_role: Rol del agente que genero la respuesta.
            ttl_seconds: TTL personalizado (usa default si None).
            metadata: Metadatos adicionales.

        Returns:
            True si se almaceno correctamente.
        """
        self._stats["sets"] += 1
        now = datetime.now(UTC).isoformat()
        prompt_hash = self._hash_prompt(prompt)
        effective_ttl = ttl_seconds or self._default_ttl

        # --- Fix #5: eliminar [PENDING] previo para evitar duplicados ---
        if self._try_remove_pending(prompt_hash):
            logger.debug(
                "SemanticCache removed [PENDING] (hash=%s, agent=%s)",
                prompt_hash[:8], agent_role,
            )

        entry = CacheEntry(
            prompt_hash=prompt_hash,
            prompt_text=prompt,
            response=response,
            agent_role=agent_role,
            created_at=now,
            last_accessed=now,
            ttl_seconds=effective_ttl,
            metadata=metadata or {},
        )

        # Generar embedding
        vec = self._embedding_fn(prompt)

        # Metadata para LanceDB
        lancedb_meta = entry.to_dict()
        lancedb_meta["response"] = response  # asegurar que response este presente
        lancedb_meta["prompt_text_short"] = prompt[:200]

        try:
            self._store.insert(
                COLLECTION_SEMANTIC_CACHE,
                vec.reshape(1, -1),
                [lancedb_meta],
            )
            logger.debug(
                "SemanticCache SET (hash=%s, agent=%s, len=%d chars)",
                prompt_hash[:8], agent_role, len(response),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("SemanticCache set failed: %s", exc)
            return False

    def get_stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        stats = dict(self._stats)
        total = stats.get("total_requests", 1)
        stats["hit_rate"] = (
            round(stats.get("hits", 0) / max(total, 1) * 100, 1)
            if total > 0
            else 0.0
        )
        stats["collection"] = COLLECTION_SEMANTIC_CACHE
        stats["threshold"] = self._threshold
        stats["default_ttl_seconds"] = self._default_ttl
        return stats

    def clear(self) -> int:
        """
        Limpiar todas las entradas del cache.

        Returns:
            Numero de entradas eliminadas.
        """
        try:
            existing = self._store.list_collections()
            if COLLECTION_SEMANTIC_CACHE in existing:
                self._store.delete_collection(COLLECTION_SEMANTIC_CACHE)
                self._ensure_collection()
                logger.info("SemanticCache cleared")
                return 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("SemanticCache clear failed: %s", exc)
        return 0

    def clear_expired(self) -> int:
        """
        Eliminar entradas expiradas del cache.

        Recorre todas las entradas, verifica expiracion por ``created_at``
        y ``ttl_seconds``, y elimina las que han expirado tanto en LanceDB
        como en el fallback in-memory.

        Returns:
            Numero de entradas eliminadas.
        """
        removed = 0
        try:
            if self._store._lancedb_available and self._store._db is not None:
                tbl = self._store._db.open_table(COLLECTION_SEMANTIC_CACHE)
                # Escanear con limite alto para cubrir toda la tabla
                all_entries = tbl.search().limit(100000).to_list()
                for entry in all_entries:
                    created_at = entry.get("created_at", "")
                    ttl = entry.get("ttl_seconds", self._default_ttl)
                    if self._is_expired(created_at, ttl):
                        prompt_hash = entry.get("prompt_hash", "")
                        if prompt_hash:
                            tbl.delete(f"prompt_hash = '{prompt_hash}'")
                            removed += 1
            else:
                # Fallback in-memory
                col = self._store._mem_collections.get(COLLECTION_SEMANTIC_CACHE)
                if col:
                    to_delete = [
                        key
                        for key, item in col.items.items()
                        if self._is_expired(
                            item.metadata.get("created_at", ""),
                            item.metadata.get("ttl_seconds", self._default_ttl),
                        )
                    ]
                    for key in to_delete:
                        del col.items[key]
                        removed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("SemanticCache clear_expired failed: %s", exc)

        if removed > 0:
            logger.info("SemanticCache eliminated %d expired entries", removed)
        return removed
