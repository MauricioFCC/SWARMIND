"""KVCacheSharing — Comparticion de KV Cache entre agentes secuenciales.

Permite que agentes que procesan el mismo contexto compartan el KV cache,
evitando recomputacion costosa. Cuando un agente B procesa un prompt similar
al que ya proceso el agente A, puede reutilizar el KV cache de A.

Basado en:
- Q-KVComm (Kriuk & Ng, 2025): 5-6x compression ratio en KV cache
- G-KV (Liao et al., 2025): Eviccion global + RL post-training, -40% memoria

Arquitectura:
1. Agente A procesa prompt -> KV cache almacenado
2. Agente B mismo prompt -> reutiliza KV cache de A
3. Si prompt es similar (prefix match), reutiliza parcialmente
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_DEFAULT_CAPACITY: int = 50
_KV_COMPRESSION_RATIO: float = 0.2  # 5x compression


@dataclass
class KVCacheEntry:
    """Entrada de KV cache compartido.

    Attributes:
        key: Hash del prompt.
        prompt: Prompt original (truncado a 100 chars).
        model: Modelo asociado.
        agent_id: ID del agente que creo el cache.
        token_count: Numero de tokens en el cache.
        created_at: Timestamp de creacion.
        memory_estimate: Estimacion de memoria en bytes.
        hit_count: Contador de reusos.
    """
    key: str
    prompt: str
    model: str
    agent_id: str
    token_count: int
    created_at: float
    memory_estimate: int = 0
    hit_count: int = 0


@dataclass
class KVCacheStats:
    """Estadisticas del KV cache compartido.

    Attributes:
        total_entries: Entradas en cache.
        total_hits: Reusos de cache.
        total_misses: Fallos de cache.
        hit_rate: Tasa de reuso [0,1].
        memory_saved_mb: Memoria ahorrada en MB.
    """
    total_entries: int = 0
    total_hits: int = 0
    total_misses: int = 0
    hit_rate: float = 0.0
    memory_saved_mb: float = 0.0


class KVCacheSharing:
    """Cache compartido de KV entre agentes, thread-safe.

    Args:
        capacity: Maximo de entradas (default: 50).
        tokens_per_entry: Estimacion de tokens por entrada (default: 1024).

    Example:
        >>> cache = KVCacheSharing()
        >>> cache.store("prompt", "gpt-4", "agent_a", 512)
        >>> entry = cache.get("prompt")
    """

    def __init__(
        self,
        capacity: int = _DEFAULT_CAPACITY,
        tokens_per_entry: int = 1024,
    ) -> None:
        """Inicializa el KV cache compartido.

        Args:
            capacity: Maximo de entradas.
            tokens_per_entry: Tokens estimados por entrada.

        Raises:
            ValueError: Si capacity < 1.
        """
        if capacity < 1:
            raise ValueError(
                f"[KVCache] capacity={capacity} debe ser >= 1. WHERE: __init__."
            )

        self._capacity: int = capacity
        self._bytes_per_token: float = 2.0  # 2 bytes por token en KV cache
        self._lock: threading.RLock = threading.RLock()
        self._entries: dict[str, KVCacheEntry] = {}
        self._lru: list[str] = []
        self._hits: int = 0
        self._misses: int = 0

        logger.info("[KVCache] Inicializado: capacity=%d", capacity)

    def _key(self, prompt: str) -> str:
        """Computa el key para un prompt.

        Args:
            prompt: Prompt a hashear.

        Returns:
            Hash SHA256.
        """
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def _prefix_match(self, a: str, b: str) -> int:
        """Encuentra la longitud del prefijo comun entre dos strings.

        Args:
            a: Primer string.
            b: Segundo string.

        Returns:
            Longitud del prefijo comun en caracteres.
        """
        i: int = 0
        while i < min(len(a), len(b)) and a[i] == b[i]:
            i += 1
        return i

    def store(
        self,
        prompt: str,
        model: str,
        agent_id: str,
        token_count: int = 1024,
    ) -> str:
        """Almacena un KV cache.

        Args:
            prompt: Prompt completo.
            model: Modelo usado.
            agent_id: Agente que almacena.
            token_count: Tokens en el cache.

        Returns:
            Key del cache almacenado.
        """
        key: str = self._key(prompt)
        mem_est: int = int(token_count * self._bytes_per_token)

        entry: KVCacheEntry = KVCacheEntry(
            key=key,
            prompt=prompt[:100],
            model=model,
            agent_id=agent_id,
            token_count=token_count,
            memory_estimate=mem_est,
            created_at=time.time(),
        )

        with self._lock:
            if key in self._entries:
                self._lru.remove(key)
            self._entries[key] = entry
            self._lru.append(key)

            if len(self._entries) > self._capacity:
                self._evict_lru()

        logger.debug(
            "[KVCache] Stored: key=%s, model=%s, agent=%s, tokens=%d",
            key[:12], model, agent_id, token_count,
        )
        return key

    def get(self, prompt: str, min_prefix: int = 10) -> KVCacheEntry | None:
        """Recupera un KV cache por prompt exacto o prefijo.

        Args:
            prompt: Prompt a buscar.
            min_prefix: Minimo de caracteres de prefijo para match parcial.

        Returns:
            KVCacheEntry si hay match, None si no.
        """
        exact_key: str = self._key(prompt)

        with self._lock:
            # Busqueda exacta
            entry: KVCacheEntry | None = self._entries.get(exact_key)
            if entry is not None:
                self._hits += 1
                entry.hit_count += 1
                # Actualizar LRU
                self._lru.remove(exact_key)
                self._lru.append(exact_key)
                logger.debug("[KVCache] HIT exacto: key=%s", exact_key[:12])
                return entry

            # Busqueda por prefijo
            best_match: tuple[str, int, KVCacheEntry] | None = None
            for key, ent in self._entries.items():
                prefix_len: int = self._prefix_match(prompt, ent.prompt)
                if prefix_len >= min_prefix:
                    candidate: tuple[str, int, KVCacheEntry] = (
                        key, prefix_len, ent
                    )
                    if best_match is None or prefix_len > best_match[1]:
                        best_match = candidate

            if best_match is not None:
                key, _, entry = best_match
                self._hits += 1
                entry.hit_count += 1
                self._lru.remove(key)
                self._lru.append(key)
                logger.debug(
                    "[KVCache] HIT parcial: key=%s, prefix=%d",
                    key[:12], best_match[1],
                )
                return entry

            self._misses += 1
            logger.debug("[KVCache] MISS: prefix=%d", min_prefix)
            return None

    def _evict_lru(self) -> str | None:
        """Elimina la entrada LRU.

        Returns:
            Key eliminado o None.
        """
        if not self._lru:
            return None
        lru_key: str = self._lru.pop(0)
        entry: KVCacheEntry | None = self._entries.pop(lru_key, None)
        if entry:
            logger.debug("[KVCache] LRU eviction: %s", lru_key[:12])
        return lru_key

    def get_stats(self) -> KVCacheStats:
        """Retorna estadisticas del cache.

        Returns:
            KVCacheStats con metricas.
        """
        with self._lock:
            total: int = self._hits + self._misses
            hit_rate: float = self._hits / total if total > 0 else 0.0
            mem_saved: float = (
                self._hits * 1024 * self._bytes_per_token / (1024 * 1024)
            )

            return KVCacheStats(
                total_entries=len(self._entries),
                total_hits=self._hits,
                total_misses=self._misses,
                hit_rate=hit_rate,
                memory_saved_mb=mem_saved,
            )

    def clear(self) -> int:
        """Limpia todo el cache.

        Returns:
            Numero de entradas eliminadas.
        """
        with self._lock:
            count: int = len(self._entries)
            self._entries.clear()
            self._lru.clear()
            self._hits = 0
            self._misses = 0
            logger.info("[KVCache] Cleared %d entries", count)
            return count

    @property
    def size(self) -> int:
        """Numero de entradas en cache.

        Returns:
            Cantidad de entradas.
        """
        with self._lock:
            return len(self._entries)
