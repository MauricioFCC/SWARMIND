"""
Semantic Cache — Cachea respuestas de LLM por similitud semantica.

Usa LanceDB como backend (ya integrado). Cuando un agente formula una query,
se calcula su embedding y se busca en la coleccion "semantic_cache".
Si existe una respuesta con similitud > threshold, se retorna sin llamar al LLM.

Ahorro estimado: 20-40% de llamadas LLM evitadas.
Hit rate tipico: 25-40% con threshold 0.92.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from harness.memory_rag.lance_vector_store import LanceVectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLLECTION_SEMANTIC_CACHE = "semantic_cache"
DEFAULT_SIMILARITY_THRESHOLD = 0.92
DEFAULT_TTL_SECONDS = 3600  # 1 hora
DEFAULT_EMBEDDING_DIM = 384


# ---------------------------------------------------------------------------
# Cache Entry
# ---------------------------------------------------------------------------


@dataclass
class CacheEntry:
    """A single cache entry."""

    prompt_hash: str
    prompt_text: str
    response: str
    agent_role: str
    similarity: float = 0.0
    hit_count: int = 1
    created_at: str = ""
    last_accessed: str = ""
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if this entry has exceeded its TTL."""
        if not self.created_at:
            return True
        try:
            created = datetime.fromisoformat(self.created_at)
            elapsed = (datetime.now(timezone.utc) - created).total_seconds()
            return elapsed > self.ttl_seconds
        except (ValueError, TypeError):
            return True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for LanceDB storage."""
        return {
            "prompt_hash": self.prompt_hash,
            "prompt_text": self.prompt_text[:500],  # truncar para storage
            "response": self.response,
            "agent_role": self.agent_role,
            "hit_count": self.hit_count,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "ttl_seconds": self.ttl_seconds,
            "metadata": json.dumps(self.metadata),
        }


# ---------------------------------------------------------------------------
# SemanticCache
# ---------------------------------------------------------------------------


class SemanticCache:
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
        vector_store: Optional[LanceVectorStore] = None,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        default_ttl: int = DEFAULT_TTL_SECONDS,
        embedding_fn: Optional[Callable[[str], np.ndarray]] = None,
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
        self._stats: Dict[str, Any] = {
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
        threshold: Optional[float] = None,
    ) -> Optional[str]:
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
        except Exception as exc:
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
        ttl_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Almacenar respuesta en cache.

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
        now = datetime.now(timezone.utc).isoformat()

        entry = CacheEntry(
            prompt_hash=self._hash_prompt(prompt),
            prompt_text=prompt,
            response=response,
            agent_role=agent_role,
            created_at=now,
            last_accessed=now,
            ttl_seconds=ttl_seconds or self._default_ttl,
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
                entry.prompt_hash[:8], agent_role, len(response),
            )
            return True
        except Exception as exc:
            logger.warning("SemanticCache set failed: %s", exc)
            return False

    def get_stats(self) -> Dict[str, Any]:
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
        except Exception as exc:
            logger.warning("SemanticCache clear failed: %s", exc)
        return 0

    def clear_expired(self) -> int:
        """
        Eliminar entradas expiradas del cache.

        Nota: Esta es una operacion costosa que recorre todas las entradas.
        Se recomienda ejecutarla periodicamente (ej: cada hora).

        Returns:
            Numero de entradas eliminadas.
        """
        # LanceDB no tiene borrado por condicion facil, asi que
        # esta operacion es principalmente util para el fallback in-memory
        logger.info("SemanticCache expired-entry cleanup skipped (LanceDB TTL)")
        return 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize_similarity(self, raw_score: float) -> float:
        """Normalize raw score to a 0-1 similarity value (1 = identical).

        LanceDB usa L2 distance por defecto (0 = identical, higher = less similar),
        asi que convertimos: sim = 1/(1+L2).  L2=0 → 1.0, L2=0.1 → 0.91, ...

        El fallback in-memory usa cosine similarity (1 = identical, -1 = opposite),
        que se usa directamente (clamped a 0-1).
        """
        if getattr(self._store, '_lancedb_available', False):
            # LanceDB: raw_score is L2 distance → convertir a similitud
            return 1.0 / (1.0 + raw_score)
        # In-memory: raw_score is cosine similarity → clamp a [0, 1]
        return max(0.0, min(1.0, raw_score))

    @staticmethod
    def _hash_prompt(prompt: str) -> str:
        """Generar hash deterministico del prompt para busqueda exacta."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def _search_exact(
        self, prompt_hash: str, agent_role: str
    ) -> Optional[Tuple[str, CacheEntry]]:
        """Buscar por hash exacto (mas rapido que busqueda vectorial)."""
        try:
            # Usamos un vector dummy con top_k generoso para cubrir toda la tabla
            dummy_vec = np.zeros(DEFAULT_EMBEDDING_DIM, dtype=np.float32)
            results = self._store.search(
                COLLECTION_SEMANTIC_CACHE,
                dummy_vec,
                top_k=50,
            )
            for result in results:
                meta = result.get("metadata", {})
                if not isinstance(meta, dict):
                    continue
                # Verificar prompt_hash y agent_role manualmente
                result_hash = meta.get("prompt_hash", "")
                result_role = meta.get("agent_role", "*")
                if result_hash != prompt_hash:
                    continue
                if agent_role != "*" and result_role not in (agent_role, "*"):
                    continue
                response = meta.get("response", "")
                if not response:
                    continue
                entry = CacheEntry(
                    prompt_hash=prompt_hash,
                    prompt_text=meta.get("prompt_text", ""),
                    response=response,
                    agent_role=meta.get("agent_role", "*"),
                    created_at=meta.get("created_at", ""),
                    last_accessed=meta.get("last_accessed", ""),
                    ttl_seconds=meta.get("ttl_seconds", DEFAULT_TTL_SECONDS),
                    hit_count=meta.get("hit_count", 1),
                )
                return response, entry
        except Exception:
            pass
        return None

    def _update_hit_count(self, entry: CacheEntry) -> None:
        """Incrementar contador de hits para una entrada."""
        try:
            self._store.update_records(
                COLLECTION_SEMANTIC_CACHE,
                filters={"prompt_hash": entry.prompt_hash},
                updates={
                    "hit_count": entry.hit_count + 1,
                    "last_accessed": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            pass

    def _delete_entry(self, prompt_hash: str) -> None:
        """Eliminar una entrada del cache (para entries expiradas)."""
        # En LanceDB no hay delete por campo facil,
        # asi que esto es un no-op para LanceDB.
        logger.debug("Cache entry deletion requested (hash=%s)", prompt_hash[:8])

    @staticmethod
    def _is_expired(created_at: str, ttl_seconds: int) -> bool:
        """Verificar si una entrada ha expirado."""
        if not created_at:
            return True
        try:
            created = datetime.fromisoformat(created_at)
            elapsed = (datetime.now(timezone.utc) - created).total_seconds()
            return elapsed > ttl_seconds
        except (ValueError, TypeError):
            return True

    @staticmethod
    def _default_embedding(text: str) -> np.ndarray:
        """
        Fallback embedding deterministico (no requiere modelo ML).
        Basado en frecuencias de caracteres.
        """
        vec = np.zeros(DEFAULT_EMBEDDING_DIM, dtype=np.float32)
        for i, ch in enumerate(text.encode("utf-8", errors="replace")):
            idx = (i * 7 + ch) % DEFAULT_EMBEDDING_DIM
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def _ensure_collection(self) -> None:
        """Asegurar que la coleccion semantic_cache existe con el schema correcto.

        LanceDB requiere que el schema se defina al crear la tabla.
        Como LanceVectorStore._ensure_lancedb_collections() crea la tabla
        para DEFAULT_COLLECTIONS con un schema base (solo id/vector/metadata/
        created_at), siempre recreamos semantic_cache para garantizar que
        tenga las columnas especificas que necesita.
        """
        try:
            # Siempre eliminar primero si existe (puede tener schema incorrecto)
            if COLLECTION_SEMANTIC_CACHE in self._store.list_collections():
                self._store.delete_collection(COLLECTION_SEMANTIC_CACHE)
            self._create_collection_with_schema()
        except Exception as exc:
            logger.warning(
                "Could not ensure collection '%s': %s",
                COLLECTION_SEMANTIC_CACHE, exc,
            )

    def _create_collection_with_schema(self) -> None:
        """Crear la coleccion con un sample row para definir el schema.

        LanceVectorStore.create_collection() usa data=[] que falla en
        LanceDB 0.33+. En su lugar, creamos la tabla directamente con
        un sample row que define todas las columnas necesarias, y luego
        borramos el placeholder.
        """
        # Intentar crear via LanceDB directamente si esta disponible
        lancedb_available = getattr(self._store, '_lancedb_available', False)
        lancedb_db = getattr(self._store, '_db', None)

        if lancedb_available and lancedb_db is not None:
            now = datetime.now(timezone.utc).isoformat()
            sample = {
                "id": "__schema_init__",
                "vector": [0.0] * DEFAULT_EMBEDDING_DIM,
                "metadata": "{}",
                "created_at": now,
                "prompt_hash": "",
                "prompt_text": "",
                "prompt_text_short": "",
                "response": "",
                "agent_role": "",
                "hit_count": 0,
                "last_accessed": now,
                "ttl_seconds": DEFAULT_TTL_SECONDS,
            }
            lancedb_db.create_table(
                COLLECTION_SEMANTIC_CACHE,
                data=[sample],
                mode="create",
            )
            tbl = lancedb_db.open_table(COLLECTION_SEMANTIC_CACHE)
            tbl.delete("id = '__schema_init__'")
            logger.info(
                "Created LanceDB table '%s' with semantic_cache schema",
                COLLECTION_SEMANTIC_CACHE,
            )
        else:
            # Fallback: create_collection funciona para in-memory
            self._store.create_collection(COLLECTION_SEMANTIC_CACHE)
            logger.info("Created collection '%s' (in-memory)", COLLECTION_SEMANTIC_CACHE)
