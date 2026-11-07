"""Actor y batcher de escritura single-writer (Spec ruscadb-async-io).

RuscaDB es un motor embebido single-writer: el handle debe tocarse desde un
solo hilo. Este modulo implementa:

  - ``WriteActor``: un hilo dedicado + cola acotada con backpressure tipado.
  - ``WriteBatcher``: coalescing de inserts con flush por tamano o por
    ``max_delay`` (para no colgar trafico bajo).

Referencia: SQLite WAL (un solo writer) y DuckDB (single write owner).
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from concurrent.futures import Future
from typing import Any

logger = logging.getLogger(__name__)

#: Tamano por defecto de la cola del actor de escritura.
DEFAULT_WRITE_QUEUE_SIZE = 256


class MemoryBackpressureError(RuntimeError):
    """La cola del actor de escritura esta llena (backpressure explicito)."""


class WriteActor:
    """Actor de escritura: un hilo dedicado y una cola acotada.

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

    def submit(
        self, func: Any, *args: Any, timeout: float = 30.0, **kwargs: Any
    ) -> Any:
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
        self._enqueue((future, func, args, kwargs))
        return future.result(timeout=timeout)

    def _enqueue(self, item: tuple[Any, ...]) -> None:
        """Encola una tarea o falla con backpressure tipado."""
        try:
            self._queue.put_nowait(item)
        except queue.Full as exc:
            raise MemoryBackpressureError(
                "WriteActor | WHAT=cola_llena | "
                f"WHY=backpressure | WHERE=submit | pendientes={self.pending}"
            ) from exc

    def _run(self) -> None:
        """Bucle del hilo: consume tareas hasta recibir el centinela ``None``."""
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            self._execute(item)
            self._queue.task_done()

    @staticmethod
    def _execute(item: tuple[Any, Any, tuple, dict]) -> None:
        """Ejecuta una tarea y publica resultado/excepcion en su future."""
        future, func, args, kwargs = item
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(func(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - se propaga al llamador
            future.set_exception(exc)

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
    """Coalesce inserciones en lotes antes de tocar el motor.

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
        self._add(collection, vectors, metadata, texts, future)
        self._wait_or_flush(future, collection)
        return future.result(timeout=timeout)

    def _add(
        self,
        collection: str,
        vectors: Any,
        metadata: list[dict[str, Any]],
        texts: list[str] | None,
        future: Future[list[str]],
    ) -> None:
        """Agrega la peticion al lote y dispara el flush si esta completo."""
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

    def _wait_or_flush(self, future: Future[Any], collection: str) -> None:
        """Espera ``max_delay`` y fuerza el flush si el lote no se completo."""
        deadline = time.monotonic() + self._max_delay
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.001)
        if not future.done():
            with self._lock:
                self._flush_locked(collection)

    def flush(self) -> int:
        """Fuerza el flush de todos los lotes pendientes.

        Returns:
            Numero de inserts enviados al motor.
        """
        with self._lock:
            return sum(
                self._flush_locked(collection)
                for collection in list(self._pending)
            )

    def _flush_locked(self, collection: str) -> int:
        """Ejecuta un insert agregado (debe llamarse con el lock tomado)."""
        batch = self._pending.pop(collection, [])
        if not batch:
            return 0
        stacked, counts, metadata, texts = self._combine(batch)
        try:
            ids = self._store.insert(
                collection, stacked, metadata, **({"texts": texts} if texts else {})
            )
        except BaseException as exc:  # noqa: BLE001 - se propaga a cada future
            for item in batch:
                item["future"].set_exception(exc)
            return 0
        self._distribute(batch, counts, ids)
        return len(batch)

    @staticmethod
    def _combine(
        batch: list[dict[str, Any]]
    ) -> tuple[Any, list[int], list[dict[str, Any]], list[str]]:
        """Apila vectores y concatena metadata/textos de un lote."""
        import numpy as np

        matrices = [
            np.atleast_2d(np.asarray(item["vectors"], dtype=np.float32))
            for item in batch
        ]
        counts = [matrix.shape[0] for matrix in matrices]
        metadata: list[dict[str, Any]] = []
        texts: list[str] = []
        has_texts = any(item["texts"] for item in batch)
        for item in batch:
            metadata.extend(item["metadata"])
            if has_texts:
                row_texts = item["texts"] or []
                texts.extend(
                    row_texts[index] if index < len(row_texts) else ""
                    for index in range(len(item["metadata"]))
                )
        return np.vstack(matrices), counts, metadata, texts

    @staticmethod
    def _distribute(
        batch: list[dict[str, Any]], counts: list[int], ids: list[str]
    ) -> None:
        """Reparte los ids del lote entre los futures de cada peticion."""
        offset = 0
        for item, count in zip(batch, counts, strict=True):
            item["future"].set_result(ids[offset: offset + count])
            offset += count


__all__ = [
    "DEFAULT_WRITE_QUEUE_SIZE",
    "MemoryBackpressureError",
    "WriteActor",
    "WriteBatcher",
]
