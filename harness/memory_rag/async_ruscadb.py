"""Wrapper async sobre RuscaDBStore (Spec ruscadb-async-io).

El C-ABI de RuscaDB es sincrono (single-writer). Este adaptador expone la
misma semantica en ``async`` delegando a un hilo del executor por defecto
(``asyncio.to_thread``), y opcionalmente confina TODAS las escrituras a un
**actor** (un unico hilo con cola acotada y backpressure tipado), que es el
patron recomendado para motores embebidos single-writer (SQLite WAL/DuckDB).

Diseno:
  - Sin estado propio: envuelve un ``RuscaDBStore`` (o cualquier store con la
    misma API) y reusa su handle; no abre conexiones nuevas.
  - ``from_path`` construye el store subyacente si no se inyecta uno.
  - ``write_actor=True`` activa el actor de escritura (cola ``bounded``); al
    llenarse lanza ``MemoryBackpressureError`` en vez de bloquear el loop.
  - Compatible con ``async with`` para liberar el handle al salir.

Referencia: Spec ``ruscadb-async-io``; SQLite WAL (un solo writer) y DuckDB
(single write owner + comandos acotados).
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from concurrent.futures import Future
from typing import Any, Self

logger = logging.getLogger(__name__)

#: Tamano por defecto de la cola del actor de escritura.
DEFAULT_WRITE_QUEUE_SIZE = 256


class MemoryBackpressureError(RuntimeError):
    """La cola del actor de escritura esta llena (backpressure explicito)."""


class WriteActor:
    """Actor de escritura: un hilo dedicado y una cola acotada.

    Garantiza que el handle del motor (single-writer) solo se toca desde un
    hilo, serializando lecturas-escritura sin recurrir a locks globales.

    Args:
        store: Store sincrono subyacente.
        queue_size: Capacidad maxima de la cola; al llenarse, ``submit`` lanza
            ``MemoryBackpressureError`` (nunca bloquea).
        name: Nombre del hilo (diagnostico).
    """

    def __init__(
        self,
        store: Any,
        queue_size: int = DEFAULT_WRITE_QUEUE_SIZE,
        name: str = "ruscadb-writer",
    ) -> None:
        if queue_size <= 0:
            raise ValueError("WriteActor: queue_size debe ser positivo")
        self._store = store
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=queue_size)
        self._closed = False
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()

    @property
    def store(self) -> Any:
        """Store sincrono confinado al actor."""
        return self._store

    @property
    def pending(self) -> int:
        """Numero de tareas en cola (telemetria de backpressure)."""
        return self._queue.qsize()

    def submit(self, func: Any, *args: Any, timeout: float = 30.0, **kwargs: Any) -> Any:
        """Ejecuta ``func`` en el hilo del actor y espera el resultado.

        Args:
            func: Callable sincrono.
            *args: Argumentos posicionales.
            timeout: Segundos maximos de espera del resultado.
            **kwargs: Argumentos nombrados.

        Returns:
            El resultado del callable.

        Raises:
            MemoryBackpressureError: Si la cola esta llena.
            RuntimeError: Si el actor ya fue cerrado.
            TimeoutError: Si el resultado no llega en ``timeout``.
        """
        if self._closed:
            raise RuntimeError("WriteActor: actor cerrado")
        future: Future[Any] = Future()
        try:
            self._queue.put_nowait((future, func, args, kwargs))
        except queue.Full as exc:
            raise MemoryBackpressureError(
                "WriteActor | WHAT=cola_llena | "
                f"WHY=backpressure | WHERE=submit | pendientes={self.pending}"
            ) from exc
        return future.result(timeout=timeout)

    def _run(self) -> None:
        """Bucle del hilo: consume tareas hasta recibir el centinela ``None``."""
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            future, func, args, kwargs = item
            if not future.set_running_or_notify_cancel():
                self._queue.task_done()
                continue
            try:
                future.set_result(func(*args, **kwargs))
            except BaseException as exc:  # noqa: BLE001 - se propaga al llamador
                future.set_exception(exc)
            finally:
                self._queue.task_done()

    def close(self, timeout: float = 5.0) -> None:
        """Detiene el actor tras vaciar la cola (idempotente)."""
        if self._closed:
            return
        self._closed = True
        try:
            self._queue.put(None, timeout=timeout)
        except queue.Full:
            logger.warning("WriteActor: cola llena al cerrar; se corta el hilo")
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("WriteActor: el hilo no termino en %.1fs", timeout)


class WriteBatcher:
    """Coalesce inserciones en lotes antes de tocar el motor (write batching).

    Reduce el overhead por fila (commit/parseo del C-ABI) agrupando inserts de
    la misma coleccion. Si el lote no alcanza ``max_batch``, queda pendiente
    hasta ``flush()`` (llamado al cerrar o por el llamador).

    Args:
        store: Store sincrono subyacente.
        max_batch: Numero de inserts que dispara el flush.
        max_delay: Segundos maximos que un insert espera por companeros antes
            de forzar el flush (evita deadlock con trafico bajo).
    """

    def __init__(
        self, store: Any, max_batch: int = 16, max_delay: float = 0.01
    ) -> None:
        if max_batch < 2:
            raise ValueError("WriteBatcher: max_batch debe ser >= 2")
        self._store = store
        self._max_batch = int(max_batch)
        self._max_delay = max(float(max_delay), 0.0)
        self._lock = threading.Lock()
        self._pending: dict[str, list[dict[str, Any]]] = {}

    @property
    def pending(self) -> int:
        """Numero de inserts en espera de flush."""
        with self._lock:
            return sum(len(bucket) for bucket in self._pending.values())

    def submit(
        self,
        collection: str,
        vectors: Any,
        metadata: list[dict[str, Any]],
        texts: list[str] | None = None,
        timeout: float = 30.0,
    ) -> list[str]:
        """Encola un insert y espera sus ids (flushea al alcanzar el lote).

        Args:
            collection: Coleccion destino.
            vectors: Matriz o vector unico.
            metadata: Metadata por fila.
            texts: Textos explicitos por fila (opcional).
            timeout: Segundos maximos de espera.

        Returns:
            Ids logicos insertados para esta peticion.

        Raises:
            TimeoutError: Si el lote no se completa a tiempo.
        """
        future: Future[list[str]] = Future()
        with self._lock:
            bucket = self._pending.setdefault(collection, [])
            bucket.append(
                {
                    "vectors": vectors,
                    "metadata": metadata,
                    "texts": texts,
                    "future": future,
                }
            )
            if len(bucket) >= self._max_batch:
                self._flush_locked(collection)
        deadline = time.monotonic() + self._max_delay
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.001)
        if not future.done():
            with self._lock:
                self._flush_locked(collection)
        return future.result(timeout=timeout)

    def flush(self) -> int:
        """Fuerza el flush de todos los lotes pendientes.

        Returns:
            Numero de inserts enviados al motor.
        """
        with self._lock:
            sent = 0
            for collection in list(self._pending):
                sent += self._flush_locked(collection)
            return sent

    def _flush_locked(self, collection: str) -> int:
        """Ejecuta un insert agregado (debe llamarse con el lock tomado)."""
        import numpy as np

        batch = self._pending.pop(collection, [])
        if not batch:
            return 0
        matrices = [np.atleast_2d(np.asarray(item["vectors"], dtype=np.float32))
                    for item in batch]
        counts = [matrix.shape[0] for matrix in matrices]
        stacked = np.vstack(matrices)
        metadata: list[dict[str, Any]] = []
        texts: list[str] = []
        texts_present = any(item["texts"] for item in batch)
        for item in batch:
            metadata.extend(item["metadata"])
            if texts_present:
                row_texts = item["texts"] or []
                texts.extend(row_texts[i] if i < len(row_texts) else ""
                             for i in range(len(item["metadata"])))
        try:
            ids = self._store.insert(
                collection,
                stacked,
                metadata,
                **({"texts": texts} if texts_present else {}),
            )
        except BaseException as exc:  # noqa: BLE001 - se propaga a cada future
            for item in batch:
                item["future"].set_exception(exc)
            return 0
        offset = 0
        for item, count in zip(batch, counts, strict=True):
            item["future"].set_result(ids[offset: offset + count])
            offset += count
        return len(batch)


class AsyncRuscaDBStore:
    """Wrapper async que delega en un store sincrono via ``to_thread``.

    Args:
        store: Store sincrono subyacente (``RuscaDBStore`` o compatible).
        executor: Executor opcional; ``None`` usa el hilo del loop.
        write_actor: Si True, las escrituras se confinan a un ``WriteActor``
            (single-writer con cola acotada).
        queue_size: Capacidad de la cola del actor.
        batch_size: Si > 1, agrupa inserts en lotes de ese tamano.
        read_through_actor: Si True, las lecturas tambien pasan por el actor
            (serializacion estricta; por defecto lecturas en paralelo).
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

    async def _write(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Ejecuta una escritura (actor si esta activo; si no, ``to_thread``).

        Args:
            func: Callable de escritura.
            *args: Argumentos posicionales.
            **kwargs: Argumentos nombrados.

        Returns:
            El resultado del callable.
        """
        if self._actor is None:
            return await self._run(func, *args, **kwargs)
        return await self._run(self._actor.submit, func, *args, **kwargs)

    async def _read(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Ejecuta una lectura (por el actor si ``read_through_actor``).

        Args:
            func: Callable de lectura.
            *args: Argumentos posicionales.
            **kwargs: Argumentos nombrados.

        Returns:
            El resultado del callable.
        """
        if self._actor is not None and self._read_through_actor:
            return await self._run(self._actor.submit, func, *args, **kwargs)
        return await self._run(func, *args, **kwargs)

    async def search(
        self, collection: str, query_vector: Any, top_k: int = 5, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Busqueda densa asincrona (KNN).

        Args:
            collection: Coleccion destino.
            query_vector: Vector de consulta.
            top_k: Numero de vecinos.
            **kwargs: Opciones de gobernanza (``filters``/``trust``/``recency``).

        Returns:
            Lista de resultados ordenada por cercania.
        """
        return await self._read(
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
            **kwargs: Opciones de gobernanza (``filters``/``trust``/``recency``).

        Returns:
            Lista fusionada por Reciprocal Rank Fusion.
        """
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
        """Inserta vectores + metadata (por el actor si esta activo).

        Args:
            collection: Coleccion destino.
            vectors: Matriz ``(n, dim)`` o vector unico.
            metadata: Metadata por fila.
            **kwargs: Argumentos extra del store (p. ej. ``texts``).

        Returns:
            Ids logicos insertados.
        """
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
        """Marca uso de registros (refuerzo por recencia), via actor.

        Args:
            collection: Coleccion de los registros.
            ids: Ids usados en el retrieval.
            now: Timestamp ISO opcional.

        Returns:
            Numero de registros actualizados.
        """
        return await self._write(
            self._store.record_access, collection, ids, now=now
        )

    async def full_text_search(
        self, collection: str, query: str, top_k: int = 10, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Busqueda lexical asincrona (BM25).

        Args:
            collection: Coleccion destino.
            query: Texto de consulta.
            top_k: Numero maximo de resultados.
            **kwargs: Opciones de gobernanza (``filters``/``trust``/``recency``).

        Returns:
            Lista ordenada por relevancia lexical.
        """
        return await self._read(
            self._store.full_text_search, collection, query, top_k=top_k, **kwargs
        )

    async def delete(self, collection: str, ids: list[str]) -> int:
        """Elimina registros por id (por el actor si esta activo).

        Args:
            collection: Coleccion destino.
            ids: Ids a borrar.

        Returns:
            Numero de registros eliminados.
        """
        return await self._write(self._store.delete, collection, ids)

    async def execute(self, sql: str) -> Any:
        """Ejecuta RQL de forma asincrona.

        Args:
            sql: Sentencia RQL.

        Returns:
            Resultado crudo del motor (JSON serializado).
        """
        return await self._run(self._store.execute, sql)

    async def close(self) -> None:
        """Flushea lotes pendientes y cierra actor + store subyacente."""
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
