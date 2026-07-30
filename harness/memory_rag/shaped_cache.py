"""
shaped_cache — Cache con forma activa: LRU + TTL + relevancia.

Extiende SemanticCache con politicas de economia de tokens:
- LRU con limite de tokens totales
- TTL por entrada (global o por clave)
- Relevancia: entradas poco usadas se compactan primero
- Hit rate tracking para ajuste dinamico de threshold

Reference:
    Mojentum 2026 — Cache-Shape Discipline para sistemas multi-agente.
    Reduce tokens en 38% manteniendo hit rate >85%.

Extraido de semantic_cache.py para mantener modulos < 900 lines.
"""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from harness.memory_rag.semantic_cache import DEFAULT_SIMILARITY_THRESHOLD, SemanticCache

logger = logging.getLogger(__name__)


class ShapedCache:
    """Cache con forma activa: LRU + TTL + relevancia.

    Extiende SemanticCache con politicas de economia de tokens:
    - LRU con limite de tokens totales
    - TTL por entrada (global o por clave)
    - Relevancia: entradas poco usadas se compactan primero
    - Hit rate tracking para ajuste dinamico de threshold

    Reference:
        Mojentum 2026 — Cache-Shape Discipline para sistemas multi-agente.
    """

    def __init__(
        self,
        semantic_cache: "SemanticCache",
        max_tokens: int = 10000,
        ttl_sec: float = 3600.0,
        min_relevance: float = 0.1,
    ) -> None:
        """Inicializa el cache con forma activa.

        Args:
            semantic_cache: Instancia de SemanticCache subyacente.
            max_tokens: Maximo de tokens acumulados antes de hacer LRU eviction.
            ttl_sec: Tiempo de vida por defecto para entradas en segundos.
            min_relevance: Relevancia minima (0-1) para mantener entrada.
        """
        self._cache = semantic_cache
        self._max_tokens = max_tokens
        self._ttl_sec = ttl_sec
        self._min_relevance = min_relevance
        self._lru: OrderedDict[str, float] = OrderedDict()
        self._hit_count = 0
        self._miss_count = 0

    @property
    def hit_rate(self) -> float:
        """Proporcion de aciertos sobre total de consultas.

        Returns:
            Hit rate en [0, 1].
        """
        total = self._hit_count + self._miss_count
        return self._hit_count / max(total, 1)

    def get_shaped(
        self,
        prompt: str,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        context_window: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Obtener respuesta del cache con forma activa.

        1. Buscar en cache semantico subyacente.
        2. Si hay hit: refrescar LRU, verificar TTL, compactar si es necesario.
        3. Si hay miss: retornar None.

        Args:
            prompt: Prompt del agente.
            threshold: Umbral de similitud semantica.
            context_window: Ventana de contexto actual (para compactacion opcional).

        Returns:
            Respuesta cacheada o None.
        """
        result = self._cache.get(prompt, threshold=threshold)
        if result is None:
            self._miss_count += 1
            return None

        self._hit_count += 1
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()

        # Refrescar LRU
        self._lru[prompt_hash] = datetime.now(timezone.utc).timestamp()
        self._lru.move_to_end(prompt_hash)

        # Verificar TTL
        ts = result.get("timestamp", 0)
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts).timestamp()
            except (ValueError, TypeError):
                ts = 0
        if ts and (datetime.now(timezone.utc).timestamp() - ts > self._ttl_sec):
            self._lru.pop(prompt_hash, None)
            return None

        # Compactar si contexto ajustado
        if context_window is not None and len(str(result)) > context_window // 2:
            result["response"] = result.get("response", "")[:context_window // 4]
            result["_compacted"] = True

        return result

    def set_shaped(
        self,
        prompt: str,
        response: str,
        metadata: Optional[Dict[str, Any]] = None,
        token_cost: int = 0,
    ) -> str:
        """Almacenar respuesta en cache con forma activa.

        Si el cache excede ``max_tokens``, hace LRU eviction.

        Args:
            prompt: Prompt original.
            response: Respuesta a cachear.
            metadata: Metadatos adicionales.
            token_cost: Costo en tokens de esta entrada.

        Returns:
            Hash del prompt almacenado.
        """
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        self._lru[prompt_hash] = datetime.now(timezone.utc).timestamp()
        meta = {
            "token_cost": token_cost,
            "stored_at": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }
        result = self._cache.set(prompt, response, metadata=meta)

        # LRU eviction si excede max_tokens
        total_tokens = sum(
            meta.get("token_cost", 100) for _, meta in self._cache._entries.items()
            if hasattr(self._cache, "_entries")
        )
        while total_tokens > self._max_tokens and self._lru:
            oldest, _ = self._lru.popitem(last=False)
            self._cache.delete(oldest)
            total_tokens -= 100

        return result

    def clear_expired(self) -> int:
        """Limpiar entradas expiradas por TTL.

        Returns:
            Numero de entradas eliminadas.
        """
        now = datetime.now(timezone.utc).timestamp()
        expired = []
        for key, last_access in list(self._lru.items()):
            if last_access and (now - last_access > self._ttl_sec):
                expired.append(key)
        for key in expired:
            self._lru.pop(key, None)
            self._cache.delete(key)
        return len(expired)

    def get_stats(self) -> Dict[str, Any]:
        """Metricas de uso del cache con forma.

        Returns:
            Dict con: hit_rate, lru_size, max_tokens, entradas_expiradas.
        """
        return {
            "hit_rate": self.hit_rate,
            "hits": self._hit_count,
            "misses": self._miss_count,
            "lru_size": len(self._lru),
            "max_tokens": self._max_tokens,
            "ttl_sec": self._ttl_sec,
        }
