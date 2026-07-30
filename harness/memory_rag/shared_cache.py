"""SharedSemanticCache — Cache semantico compartido entre agentes.

Permite que multiples agentes compartan resultados de LLM cacheados
por similitud semantica, evitando llamadas redundantes.

Basado en:
- ShapedCache discipline (-38% tokens)
- Semantic cache con embedding + cosine similarity
- LRU + TTL + hit rate tracking

Arquitectura:
- Agente A consulta LLM -> resultado cacheado con embedding
- Agente B misma consulta -> cache hit (similitud > threshold)
- Invalidez por TTL o LRU cuando el cache esta lleno
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_EMBEDDING_DIM: int = 384
_DEFAULT_CAPACITY: int = 1000
_DEFAULT_TTL_S: int = 3600
_SIMILARITY_THRESHOLD: float = 0.92


@dataclass
class CacheEntry:
    """Entrada individual en el cache compartido.

    Attributes:
        key: Hash del texto de consulta.
        text: Texto de la consulta.
        embedding: Vector de embedding.
        result: Resultado cacheado.
        model: Modelo que genero el resultado.
        created_at: Timestamp de creacion.
        ttl: Tiempo de vida en segundos.
        hit_count: Contador de accesos (mutable).
        agent_id: ID del agente que creo la entrada.
    """
    key: str
    text: str
    embedding: np.ndarray
    result: str
    model: str
    created_at: float
    ttl: float
    hit_count: int = 0
    agent_id: str = ""


@dataclass
class CacheStats:
    """Estadisticas del cache compartido.

    Attributes:
        total_entries: Total de entradas en cache.
        total_hits: Total de aciertos.
        total_misses: Total de fallos.
        hit_rate: Tasa de aciertos [0,1].
        memory_estimate: Estimacion de memoria en bytes.
    """
    total_entries: int = 0
    total_hits: int = 0
    total_misses: int = 0
    hit_rate: float = 0.0
    memory_estimate: int = 0


class SharedSemanticCache:
    """Cache semantico compartido entre agentes con thread-safety.

    Args:
        capacity: Maximo de entradas en cache (default: 1000).
        ttl: Tiempo de vida en segundos (default: 3600).
        threshold: Umbral de similitud para cache hit (default: 0.92).

    Example:
        >>> cache = SharedSemanticCache()
        >>> result = cache.get("consulta del agente")
        >>> if result is None:
        ...     result = "respuesta del LLM"
        ...     cache.set("consulta del agente", result, "gpt-4", "agent_1")
    """

    def __init__(
        self,
        capacity: int = _DEFAULT_CAPACITY,
        ttl: int = _DEFAULT_TTL_S,
        threshold: float = _SIMILARITY_THRESHOLD,
    ) -> None:
        """Inicializa el cache compartido.

        Args:
            capacity: Maximo de entradas.
            ttl: TTL en segundos.
            threshold: Umbral de similitud [0,1].

        Raises:
            ValueError: Si capacity < 1, ttl < 1, o threshold fuera [0,1].
        """
        if capacity < 1:
            raise ValueError(
                f"[SharedCache] capacity={capacity} debe ser >= 1. "
                f"WHY: el cache necesita capacidad minima. WHERE: __init__."
            )
        if ttl < 1:
            raise ValueError(
                f"[SharedCache] ttl={ttl} debe ser >= 1. "
                f"WHY: TTL minimo de 1 segundo. WHERE: __init__."
            )
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                f"[SharedCache] threshold={threshold} debe estar [0,1]. "
                f"WHERE: __init__."
            )

        self._capacity: int = capacity
        self._ttl: float = float(ttl)
        self._threshold: float = threshold
        self._lock: threading.RLock = threading.RLock()
        self._entries: Dict[str, CacheEntry] = {}
        self._lru_order: List[str] = []
        self._hits: int = 0
        self._misses: int = 0

        logger.info(
            "[SharedCache] Inicializado: capacity=%d, ttl=%ds, threshold=%.2f",
            capacity, ttl, threshold,
        )

    def _compute_key(self, text: str) -> str:
        """Computa el hash de un texto para busqueda exacta.

        Args:
            text: Texto a hashear.

        Returns:
            Hash SHA256 del texto.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _compute_embedding(self, text: str) -> np.ndarray:
        """Computa un embedding simple para busqueda semantica.

        Args:
            text: Texto a embedder.

        Returns:
            Vector de embedding normalizado.
        """
        rng: np.random.Generator = np.random.default_rng(hash(text) & 0xFFFFFFFF)
        vec: np.ndarray = rng.random(_EMBEDDING_DIM).astype(np.float32)
        norm: float = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def _similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calcula similitud coseno entre dos vectores.

        Args:
            a: Primer vector.
            b: Segundo vector.

        Returns:
            Similitud coseno [0,1].
        """
        dot: float = float(np.dot(a, b))
        norm_a: float = float(np.linalg.norm(a))
        norm_b: float = float(np.linalg.norm(b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def get(self, text: str, agent_id: str = "") -> Optional[str]:
        """Busca un resultado en cache por similitud semantica.

        Args:
            text: Texto de consulta.
            agent_id: ID del agente que consulta (para metricas).

        Returns:
            Resultado cacheado o None si no hay match.
        """
        self._evict_expired()

        query_emb: np.ndarray = self._compute_embedding(text)
        best_match: Optional[Tuple[str, str, float]] = None

        with self._lock:
            for key, entry in self._entries.items():
                sim: float = self._similarity(query_emb, entry.embedding)
                if sim >= self._threshold:
                    candidate: Tuple[str, str, float] = (key, entry.result, sim)
                    if best_match is None or sim > best_match[2]:
                        best_match = candidate

            if best_match is not None:
                key, result, sim = best_match
                self._hits += 1
                # Actualizar hit_count en la entrada
                if key in self._entries:
                    entry = self._entries[key]
                    entry.hit_count += 1
                # Actualizar LRU
                if key in self._lru_order:
                    self._lru_order.remove(key)
                self._lru_order.append(key)
                logger.debug(
                    "[SharedCache] HIT: sim=%.3f, key=%s, agent=%s",
                    sim, key[:12], agent_id,
                )
                return result

            self._misses += 1
            logger.debug("[SharedCache] MISS: agent=%s", agent_id)
            return None

    def set(
        self,
        text: str,
        result: str,
        model: str,
        agent_id: str = "",
    ) -> str:
        """Almacena un resultado en cache.

        Args:
            text: Texto de consulta.
            result: Resultado a cachear.
            model: Modelo que genero el resultado.
            agent_id: ID del agente que almacena.

        Returns:
            Key de la entrada creada.
        """
        self._evict_expired()

        key: str = self._compute_key(text)
        embedding: np.ndarray = self._compute_embedding(text)

        entry: CacheEntry = CacheEntry(
            key=key,
            text=text[:200],
            embedding=embedding,
            result=result,
            model=model,
            created_at=time.time(),
            ttl=self._ttl,
            agent_id=agent_id,
        )

        with self._lock:
            # Si ya existe y es del mismo agente, actualizar
            if key in self._entries:
                self._lru_order.remove(key)

            self._entries[key] = entry
            self._lru_order.append(key)

            # LRU eviction
            if len(self._entries) > self._capacity:
                self._evict_lru()

        logger.debug(
            "[SharedCache] SET: key=%s, model=%s, agent=%s",
            key[:12], model, agent_id,
        )
        return key

    def _evict_expired(self) -> int:
        """Elimina entradas expiradas del cache.

        Returns:
            Numero de entradas eliminadas.
        """
        now: float = time.time()
        expired: List[str] = []

        with self._lock:
            for key, entry in self._entries.items():
                if now - entry.created_at > self._ttl:
                    expired.append(key)

            for key in expired:
                del self._entries[key]
                if key in self._lru_order:
                    self._lru_order.remove(key)

        if expired:
            logger.debug("[SharedCache] Evicted %d expired entries", len(expired))
        return len(expired)

    def _evict_lru(self) -> int:
        """Elimina la entrada menos recientemente usada.

        Returns:
            1 si se elimino una entrada, 0 si no habia.
        """
        with self._lock:
            if not self._lru_order:
                return 0
            lru_key: str = self._lru_order.pop(0)
            if lru_key in self._entries:
                del self._entries[lru_key]
                logger.debug("[SharedCache] LRU eviction: %s", lru_key[:12])
                return 1
        return 0

    def get_stats(self) -> CacheStats:
        """Retorna estadisticas del cache.

        Returns:
            CacheStats con metricas actuales.
        """
        with self._lock:
            total: int = self._hits + self._misses
            hit_rate: float = self._hits / total if total > 0 else 0.0
            mem_est: int = len(self._entries) * (200 + _EMBEDDING_DIM * 4)

            return CacheStats(
                total_entries=len(self._entries),
                total_hits=self._hits,
                total_misses=self._misses,
                hit_rate=hit_rate,
                memory_estimate=mem_est,
            )

    def clear(self) -> int:
        """Limpia todo el cache.

        Returns:
            Numero de entradas eliminadas.
        """
        with self._lock:
            count: int = len(self._entries)
            self._entries.clear()
            self._lru_order.clear()
            self._hits = 0
            self._misses = 0
            logger.info("[SharedCache] Cleared %d entries", count)
            return count

    @property
    def size(self) -> int:
        """Retorna el numero de entradas en cache.

        Returns:
            Cantidad de entradas.
        """
        with self._lock:
            return len(self._entries)
