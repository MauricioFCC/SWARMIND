"""Wrapper async sobre RuscaDBStore (Spec ruscadb-async-io).

El C-ABI de RuscaDB es sincrono (single-writer). Este adaptador expone la
misma semantica en ``async`` delegando a un hilo del executor por defecto
(``asyncio.to_thread``), de modo que el event loop del orchestrator no se
bloquea durante la I/O de memoria.

Diseno:
  - Sin estado propio: envuelve un ``RuscaDBStore`` (o cualquier store con la
    misma API) y reusa su handle; no abre conexiones nuevas (RuscaDB es
    single-writer y multiplexa con su pool interno).
  - ``from_path`` construye el store subyacente si no se inyecta uno.
  - Compatible con ``async with`` para liberar el handle al salir.

Referencia: Spec ``ruscadb-async-io``; asyncio.to_thread (Python 3.9+).
"""

from __future__ import annotations

import asyncio
from typing import Any, Self


class AsyncRuscaDBStore:
    """Wrapper async que delega en un store sincrono via ``to_thread``.

    Args:
        store: Store sincrono subyacente (``RuscaDBStore`` o compatible).
        executor: Executor opcional; ``None`` usa el hilo del loop.
    """

    def __init__(self, store: Any, executor: Any = None) -> None:
        self._store = store
        self._executor = executor

    @classmethod
    def from_path(cls, db_path: str | None = None, **kwargs: Any) -> AsyncRuscaDBStore:
        """Construye el store RuscaDB y lo envuelve en async.

        Args:
            db_path: Ruta de la base (``None`` usa el default de MemoryConfig).
            **kwargs: Argumentos extra para ``RuscaDBStore`` (p. ej. ``readonly``).

        Returns:
            Instancia async lista para usarse.
        """
        from .ruscadb_store import RuscaDBStore

        return cls(RuscaDBStore(db_path=db_path, **kwargs))

    @property
    def store(self) -> Any:
        """Store sincrono subyacente (escape hatch para operaciones puntuales)."""
        return self._store

    async def _run(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Ejecuta ``func`` en un hilo sin bloquear el event loop.

        Args:
            func: Callable sincrono a ejecutar.
            *args: Argumentos posicionales.
            **kwargs: Argumentos nombrados.

        Returns:
            El resultado del callable.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, lambda: func(*args, **kwargs)
        )

    async def search(
        self, collection: str, query_vector: Any, top_k: int = 5, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Busqueda densa asincrona (KNN).

        Args:
            collection: Coleccion destino.
            query_vector: Vector de consulta.
            top_k: Numero de vecinos.
            **kwargs: Opciones de gobernanza (``trust``/``recency``).

        Returns:
            Lista de resultados ordenada por cercania.
        """
        return await self._run(
            self._store.search, collection, query_vector, top_k=top_k, **kwargs
        )

    async def hybrid_search(
        self,
        collection: str,
        query_vector: Any,
        query_text: str = "",
        top_k: int = 5,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Busqueda hibrida asincrona (KNN + BM25 con RRF).

        Args:
            collection: Coleccion destino.
            query_vector: Vector de consulta.
            query_text: Texto para la parte lexical.
            top_k: Numero de resultados fusionados.
            **kwargs: Opciones de gobernanza (``trust``/``recency``).

        Returns:
            Lista fusionada por Reciprocal Rank Fusion.
        """
        return await self._run(
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
        """Inserta vectores + metadata de forma asincrona.

        Args:
            collection: Coleccion destino.
            vectors: Matriz ``(n, dim)`` o vector unico.
            metadata: Metadata por fila.
            **kwargs: Argumentos extra del store (p. ej. ``texts``).

        Returns:
            Ids logicos insertados.
        """
        return await self._run(
            self._store.insert, collection, vectors, metadata, **kwargs
        )

    async def full_text_search(
        self, collection: str, query: str, top_k: int = 10, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Busqueda lexical asincrona (BM25).

        Args:
            collection: Coleccion destino.
            query: Texto de consulta.
            top_k: Numero maximo de resultados.
            **kwargs: Opciones de gobernanza (``trust``/``recency``).

        Returns:
            Lista ordenada por relevancia lexical.
        """
        return await self._run(
            self._store.full_text_search, collection, query, top_k=top_k, **kwargs
        )

    async def delete(self, collection: str, ids: list[str]) -> int:
        """Elimina registros por id de forma asincrona.

        Args:
            collection: Coleccion destino.
            ids: Ids a borrar.

        Returns:
            Numero de registros eliminados.
        """
        return await self._run(self._store.delete, collection, ids)

    async def execute(self, sql: str) -> Any:
        """Ejecuta RQL de forma asincrona.

        Args:
            sql: Sentencia RQL.

        Returns:
            Resultado crudo del motor (JSON serializado).
        """
        return await self._run(self._store.execute, sql)

    async def close(self) -> None:
        """Cierra el store subyacente (commit + release del handle)."""
        await self._run(self._store.close)

    async def __aenter__(self) -> Self:
        """Entra en el contexto async devolviendo el propio wrapper."""
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Cierra el store al salir del contexto async."""
        await self.close()


__all__ = ["AsyncRuscaDBStore"]
