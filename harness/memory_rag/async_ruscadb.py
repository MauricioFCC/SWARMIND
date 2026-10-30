"""Wrapper async sobre RuscaDBStore (Spec ruscadb-async-io).

El C-ABI de RuscaDB es sincrono (single-writer). Este adaptador expone la
misma semantica en ``async`` delegando a hilos (``asyncio.to_thread``),
opcionalmente con:

  - ``write_actor=True``: escrituras confinadas a un hilo dedicado con cola
    acotada y backpressure tipado (patron single-writer).
  - ``batch_size=N``: coalescing de inserts en lotes.
  - ``read_through_actor=True``: lecturas serializadas con las escrituras.

Referencia: Spec ``ruscadb-async-io``; SQLite WAL y DuckDB (single write owner).
"""

from __future__ import annotations

import asyncio
from typing import Any, Self

from .write_actor import (
    DEFAULT_WRITE_QUEUE_SIZE,
    MemoryBackpressureError,
    WriteActor,
    WriteBatcher,
)


class AsyncRuscaDBStore:
    """Wrapper async que delega en un store sincrono.

    Args:
        store: Store sincrono subyacente (``RuscaDBStore`` o compatible).
        executor: Executor opcional; ``None`` usa el hilo del loop.
        write_actor: Confina las escrituras a un ``WriteActor``.
        queue_size: Capacidad de la cola del actor.
        batch_size: Si > 1, agrupa inserts en lotes de ese tamano.
        read_through_actor: Serializa tambien las lecturas por el actor.
    """

    def __init__(
        self,
        store: Any,
        executor: Any = None,
        write_actor: bool = False,
        queue_size: int = DEFAULT_WRITE_QUEUE_SIZE,
        batch_size: int = 0,
        read_through_actor: bool = False,
    ) -> None:
        self._store = store
        self._executor = executor
        self._actor = WriteActor(store, queue_size=queue_size) if write_actor else None
        self._batcher = WriteBatcher(store, batch_size) if batch_size > 1 else None
        self._read_through_actor = read_through_actor

    @classmethod
    def from_path(
        cls,
        db_path: str | None = None,
        write_actor: bool = False,
        **kwargs: Any,
    ) -> AsyncRuscaDBStore:
        """Construye el store RuscaDB y lo envuelve en async.

        Args:
            db_path: Ruta de la base (``None`` usa el default de MemoryConfig).
            write_actor: Activa el actor de escritura.
            **kwargs: Argumentos extra para ``RuscaDBStore`` (p. ej. ``readonly``).

        Returns:
            Instancia async lista para usarse.
        """
        from .ruscadb_store import RuscaDBStore

        return cls(RuscaDBStore(db_path=db_path, **kwargs), write_actor=write_actor)

    @property
    def store(self) -> Any:
        """Store sincrono subyacente (escape hatch para operaciones puntuales)."""
        return self._store

    @property
    def write_actor(self) -> WriteActor | None:
        """Actor de escritura, si esta activo."""
        return self._actor

    @property
    def batcher(self) -> WriteBatcher | None:
        """Batcher de inserts, si esta activo."""
        return self._batcher

    async def _run(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Ejecuta ``func`` en un hilo sin bloquear el event loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, lambda: func(*args, **kwargs)
        )

    async def _write(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Ejecuta una escritura (por el actor si esta activo)."""
        if self._actor is None:
            return await self._run(func, *args, **kwargs)
        return await self._run(self._actor.submit, func, *args, **kwargs)

    async def _read(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Ejecuta una lectura (por el actor si ``read_through_actor``)."""
        if self._actor is not None and self._read_through_actor:
            return await self._run(self._actor.submit, func, *args, **kwargs)
        return await self._run(func, *args, **kwargs)

    async def search(
        self, collection: str, query_vector: Any, top_k: int = 5, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Busqueda densa asincrona (KNN)."""
        return await self._read(
            self._store.search, collection, query_vector, top_k=top_k, **kwargs
        )

    async def search_binary(
        self,
        collection: str,
        query_vector: Any,
        top_k: int = 10,
        oversample: int | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """KNN binario asincrono (1 bit + rescore exacto)."""
        return await self._read(
            self._store.search_binary,
            collection,
            query_vector,
            top_k=top_k,
            oversample=oversample,
            **kwargs,
        )

    async def hybrid_search(
        self,
        collection: str,
        query_vector: Any,
        query_text: str = "",
        top_k: int = 5,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Busqueda hibrida asincrona (KNN + BM25 con RRF)."""
        return await self._read(
            self._store.hybrid_search,
            collection,
            query_vector,
            query_text=query_text,
            top_k=top_k,
            **kwargs,
        )

    async def insert(
        self,
        collection: str,
        vectors: Any,
        metadata: list[dict[str, Any]],
        **kwargs: Any,
    ) -> list[str]:
        """Inserta vectores + metadata (batcher > actor > hilo)."""
        if self._batcher is not None:
            texts = kwargs.pop("texts", None)
            return await self._write(
                self._batcher.submit, collection, vectors, metadata, texts
            )
        return await self._write(
            self._store.insert, collection, vectors, metadata, **kwargs
        )

    async def record_access(
        self, collection: str, ids: list[str], now: str | None = None
    ) -> int:
        """Marca uso de registros (refuerzo por recencia)."""
        return await self._write(
            self._store.record_access, collection, ids, now=now
        )

    async def full_text_search(
        self, collection: str, query: str, top_k: int = 10, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Busqueda lexical asincrona (BM25)."""
        return await self._read(
            self._store.full_text_search, collection, query, top_k=top_k, **kwargs
        )

    async def delete(self, collection: str, ids: list[str]) -> int:
        """Elimina registros por id."""
        return await self._write(self._store.delete, collection, ids)

    async def execute(self, sql: str) -> Any:
        """Ejecuta RQL de forma asincrona."""
        return await self._run(self._store.execute, sql)

    async def close(self) -> None:
        """Flushea lotes, cierra el actor y el store subyacente."""
        if self._batcher is not None:
            await self._run(self._batcher.flush)
        if self._actor is not None:
            await self._run(self._actor.close)
        await self._run(self._store.close)

    async def __aenter__(self) -> Self:
        """Entra en el contexto async devolviendo el propio wrapper."""
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Cierra el actor y el store al salir del contexto async."""
        await self.close()


__all__ = [
    "DEFAULT_WRITE_QUEUE_SIZE",
    "AsyncRuscaDBStore",
    "MemoryBackpressureError",
    "WriteActor",
    "WriteBatcher",
]
