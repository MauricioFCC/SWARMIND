"""Cache de prepared statements para RuscaDB (Spec ruscadb-prepared-statements)."""

from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger("harness.memory_rag.prepared_statements")


class PreparedStatementCache:
    """Cache de statements parseados por hash de SQL."""

    def __init__(self, max_size: int = 256) -> None:
        self._max = max_size
        self._cache: dict[str, str] = {}

    def key(self, sql: str) -> str:
        """Clave canonica para un SQL."""
        return hashlib.sha256(sql.strip().encode("utf-8")).hexdigest()

    def get(self, sql: str) -> str | None:
        """Devuelve el SQL canonico cacheado o None."""
        return self._cache.get(self.key(sql))

    def put(self, sql: str) -> str:
        """Registra un SQL y devuelve su clave."""
        k = self.key(sql)
        if len(self._cache) >= self._max:
            # evict oldest (simple: clear half)
            for key in list(self._cache.keys())[: self._max // 2]:
                del self._cache[key]
        self._cache[k] = sql.strip()
        return k

    def has(self, sql: str) -> bool:
        return self.key(sql) in self._cache

    def clear(self) -> None:
        self._cache.clear()

    def stats(self) -> dict[str, int]:
        return {"size": len(self._cache), "max": self._max}

__all__ = ["PreparedStatementCache"]
