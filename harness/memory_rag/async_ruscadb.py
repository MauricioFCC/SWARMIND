"""Wrapper async sobre RuscaDBStore (Spec ruscadb-async-io)."""

from __future__ import annotations

import asyncio
from typing import Any


class AsyncRuscaDBStore:
    """Wrapper async que delega a un store sincrono via executor."""

    def __init__(self, store: Any, executor: Any = None) -> None:
        self._store = store
        self._executor = executor

    async def search(self, collection: str, query_vector: Any, top_k: int = 5) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, lambda: self._store.search(collection, query_vector, top_k=top_k)
        )

    async def insert(self, collection: str, vectors: Any, metadata: list[dict[str, Any]]) -> list[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, lambda: self._store.insert(collection, vectors, metadata)
        )

    async def full_text_search(self, collection: str, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, lambda: self._store.full_text_search(collection, query, top_k=top_k)
        )

    async def execute(self, sql: str) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, lambda: self._store.execute(sql))

__all__ = ["AsyncRuscaDBStore"]
