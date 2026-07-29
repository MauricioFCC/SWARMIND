"""PerformanceCache — Cache predictivo para respuestas de agentes.

Implementa un caché LRU con TTL configurable y tracking de hit rate
para optimizar respuestas repetitivas de agentes en el orquestrador.
"""

from __future__ import annotations
from collections import OrderedDict
from typing import Any, Optional
import time


class PerformanceCache:
    """Caché LRU con TTL para respuestas de agentes.

    Almacena pares clave-valor con expiración por tiempo y política
    de desalojo LRU cuando se supera el tamaño máximo.

    Args:
        max_size: Número máximo de entradas en el caché (default 100).
        ttl: Tiempo de vida en segundos para cada entrada (default 300.0).
    """

    def __init__(self, max_size: int = 100, ttl: float = 300.0) -> None:
        """Inicializa el PerformanceCache.

        Args:
            max_size: Capacidad máxima del caché.
            ttl: Tiempo de expiración en segundos.

        Raises:
            ValueError: Si max_size <= 0 o ttl <= 0.
        """
        if max_size <= 0:
            raise ValueError("max_size debe ser positivo")
        if ttl <= 0:
            raise ValueError("ttl debe ser positivo")

        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size: int = max_size
        self._ttl: float = ttl
        self._hits: int = 0
        self._misses: int = 0

    def get(self, key: str) -> Optional[Any]:
        """Recupera un valor del caché si existe y no ha expirado.

        Args:
            key: Clave a buscar en el caché.

        Returns:
            El valor asociado a la clave si existe y es vigente,
            None en caso contrario.
        """
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                self._hits += 1
                self._cache.move_to_end(key)
                return value
            del self._cache[key]
        self._misses += 1
        return None

    def set(self, key: str, value: Any) -> None:
        """Almacena un valor en el caché.

        Si el caché supera el tamaño máximo, desaloja la entrada
        menos recientemente usada.

        Args:
            key: Clave bajo la cual almacenar el valor.
            value: Valor a almacenar.
        """
        self._cache[key] = (value, time.time())
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    @property
    def hit_rate(self) -> float:
        """Tasa de aciertos del caché.

        Returns:
            Proporción de hits sobre el total de accesos (0.0 a 1.0).
            Retorna 0.0 si no ha habido accesos.
        """
        total = self._hits + self._misses
        return self._hits / max(total, 1)

    @property
    def size(self) -> int:
        """Cantidad actual de entradas en el caché."""
        return len(self._cache)

    def clear(self) -> None:
        """Limpia todas las entradas del caché y resetea estadísticas."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def invalidate(self, key: str) -> bool:
        """Invalida una entrada específica del caché.

        Args:
            key: Clave a invalidar.

        Returns:
            True si la clave existía y fue eliminada, False en caso contrario.
        """
        if key in self._cache:
            del self._cache[key]
            return True
        return False
