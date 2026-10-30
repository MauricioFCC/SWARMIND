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

from ..cache_threshold import AdaptiveThreshold
from ..lance_vector_store import LanceVectorStore
from .constants import (
    COLLECTION_SEMANTIC_CACHE,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_TTL_SECONDS,
    SWEEP_EVERY_N_SETS,
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
        dataset_version: str = "",
        fail_closed: bool = False,
        adaptive_threshold: bool = False,
    ) -> None:
        """
        Args:
            vector_store: Instancia de LanceVectorStore. Si None, se crea una.
            threshold: Umbral de similitud para considerar cache hit (0.0 - 1.0).
            default_ttl: TTL por defecto en segundos para nuevas entradas.
            embedding_fn: Funcion para convertir texto a vector. Si None, se usa
                         embedding de caracteres (deterministico, no requiere modelo).
            auto_create_collection: Si True, crea la coleccion si no existe.
            dataset_version: Version del dataset/modelo que produjo las
                respuestas. Forma parte de la clave: un bump invalida en bloque.
            fail_closed: Si True, un hit solo se sirve cuando la entrada trae
                ``verified=True`` (politica fail-closed de vCache); el resto se
                trata como miss.
            adaptive_threshold: Si True, el umbral se aprende por familia de
                prompt con ``record_feedback`` (vCache).
        """
        self._store = vector_store or LanceVectorStore()
        self._threshold = threshold
        self._default_ttl = default_ttl
        self._embedding_fn = embedding_fn or self._default_embedding
        self._dataset_version = dataset_version
        self._fail_closed = fail_closed
        self._adaptive = (
            AdaptiveThreshold(base=threshold, store=self._store)
            if adaptive_threshold
            else None
        )
        #: Inserts desde el ultimo barrido proactivo de expiradas (Item 3).
        self._sets_since_sweep = 0
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
        if self._adaptive is not None:
            effective_threshold = max(
                effective_threshold, self._adaptive.threshold_for(prompt)
            )

        # 1. Hash exacto (cache hit perfecto, mas rapido)
        exact_hash = self._cache_key(prompt)
        exact_result = self._search_exact(exact_hash, agent_role)
        if exact_result is not None:
            response, entry = exact_result
            if self._fail_closed and not entry.metadata.get("verified"):
                # Fail-closed: el hit exacto no esta verificado; se evalua por
                # similitud (que aplica el mismo filtro) o se trata como miss.
                exact_result = None
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

            # Version-keyed invalidation: entradas de otra version no se sirven.
            if str(meta.get("dataset_version", "")) != str(self._dataset_version):
                continue

            # Politica fail-closed: solo se sirven respuestas verificadas.
            if self._fail_closed and not meta.get("verified"):
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
        prompt_hash = self._cache_key(prompt)
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
        lancedb_meta["dataset_version"] = self._dataset_version
        lancedb_meta["verified"] = bool((metadata or {}).get("verified", False))

        try:
            self._store.insert(
                COLLECTION_SEMANTIC_CACHE,
                vec.reshape(1, -1),
                [lancedb_meta],
            )
            persistent = self._persistent_cache()
            if persistent is not None and self._native_lance() is None:
                setter = getattr(persistent, "semantic_cache_set", None)
                if callable(setter):
                    setter(
                        prompt_hash,
                        response,
                        effective_ttl,
                        {
                            "dataset_version": self._dataset_version,
                            "verified": bool((metadata or {}).get("verified", False)),
                        },
                    )
            logger.debug(
                "SemanticCache SET (hash=%s, agent=%s, len=%d chars)",
                prompt_hash[:8], agent_role, len(response),
            )
            self._maybe_sweep()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("SemanticCache set failed: %s", exc)
            return False

    def _maybe_sweep(self) -> None:
        """Barrido proactivo de entradas expiradas (best-effort).

        Cada ``SWEEP_EVERY_N_SETS`` inserts invoca ``clear_expired()`` para
        acotar la coleccion en disco sin escanear en cada ``set()``. Sin este
        sweeper el TTL solo se aplicaba en read perezoso y la coleccion crecia
        sin cota (Item 3). Si ``clear_expired`` lanza, ``set()`` no se rompe
        (degradacion suave).

        WHERE: ``SemanticCache._maybe_sweep``
        """
        self._sets_since_sweep += 1
        if self._sets_since_sweep < SWEEP_EVERY_N_SETS:
            return
        self._sets_since_sweep = 0
        try:
            removed = self.clear_expired()
            if removed:
                logger.info("SemanticCache auto-sweep: %d expired removed", removed)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SemanticCache auto-sweep failed: %s", exc)

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
        stats["dataset_version"] = self._dataset_version
        stats["fail_closed"] = self._fail_closed
        stats["adaptive_threshold"] = self._adaptive is not None
        if self._adaptive is not None:
            stats["adaptive"] = self._adaptive.stats()
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

    def record_feedback(self, prompt: str, correct: bool) -> float:
        """Registra si un hit fue correcto y ajusta el umbral (vCache).

        Args:
            prompt: Prompt que produjo el hit.
            correct: True si la respuesta cacheada fue correcta.

        Returns:
            Umbral aprendido para esa familia de prompt.

        Raises:
            RuntimeError: Si el umbral adaptativo no esta activo.
        """
        if self._adaptive is None:
            raise RuntimeError(
                "SemanticCache.record_feedback | WHAT=umbral_no_adaptativo | "
                "WHY=adaptive_threshold=False | WHERE=record_feedback"
            )
        return self._adaptive.observe(prompt, correct)

    def invalidate_version(self, version: str | None = None) -> int:
        """Invalida en bloque las entradas de otra version de dataset.

        Args:
            version: Version objetivo; ``None`` usa ``self._dataset_version``.

        Returns:
            Numero de entradas eliminadas.
        """
        target = str(self._dataset_version if version is None else version)
        removed = 0
        seen: set[str] = set()
        for meta in self._list_cache_entries():
            prompt_hash = str(meta.get("prompt_hash") or "")
            if not prompt_hash or prompt_hash in seen:
                continue
            if str(meta.get("dataset_version", "")) == target:
                continue
            seen.add(prompt_hash)
            self._delete_entry(prompt_hash)
            removed += 1
        if removed:
            logger.info("SemanticCache invalidated %d stale-version entries", removed)
        return removed

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
        persistent = self._persistent_cache()
        if persistent is not None and self._native_lance() is None:
            purger = getattr(persistent, "semantic_cache_purge_expired", None)
            if callable(purger):
                removed = int(purger(self._default_ttl) or 0)
            if removed > 0:
                logger.info("SemanticCache eliminated %d expired entries", removed)
            return removed
        try:
            db = self._native_lance()
            if db is not None:
                tbl = db.open_table(COLLECTION_SEMANTIC_CACHE)
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
                col = getattr(self._store, "_mem_collections", {}).get(
                    COLLECTION_SEMANTIC_CACHE
                )
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
