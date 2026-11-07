"""Query result cache persistente (Spec ruscadb-query-cache)."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

logger = logging.getLogger("harness.memory_rag.query_cache")


class QueryResultCache:
    """Cache de resultados de RQL con TTL e invalidacion por coleccion."""

    def __init__(self, ttl_sec: float = 300.0) -> None:
        self._ttl = ttl_sec
        self._store: dict[str, tuple[float, Any]] = {}
        self._collection_keys: dict[str, set[str]] = {}

    def key(self, sql: str, params: tuple[Any, ...] = ()) -> str:
        """Genera la clave de cache para una query."""
        payload = sql + repr(params)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, sql: str, params: tuple[Any, ...] = ()) -> Any | None:
        """Devuelve el resultado cacheado o None si expiro/no existe."""
        k = self.key(sql, params)
        entry = self._store.get(k)
        if entry is None:
            return None
        ts, value = entry
        if (time.monotonic() - ts) > self._ttl:
            del self._store[k]
            return None
        return value

    def set(self, sql: str, value: Any, params: tuple[Any, ...] = (), collection: str | None = None) -> None:
        """Almacena un resultado en cache."""
        k = self.key(sql, params)
        self._store[k] = (time.monotonic(), value)
        if collection:
            self._collection_keys.setdefault(collection, set()).add(k)

    def invalidate(self, collection: str) -> int:
        """Invalida todas las entradas de una coleccion. Devuelve cuantas."""
        keys = self._collection_keys.pop(collection, set())
        removed = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                removed += 1
        return removed

    def clear(self) -> None:
        """Vacia toda la cache."""
        self._store.clear()
        self._collection_keys.clear()

    def stats(self) -> dict[str, int]:
        """Estadisticas basicas."""
        return {"entries": len(self._store), "collections": len(self._collection_keys)}

__all__ = ["QueryResultCache"]
