"""Async I/O Fusion â€” BatchAccumulator para operaciones I/O batch.

Fusiona operaciones I/O individuales en batches para reducir round-trips
a backends (LanceDB, Chroma, Qdrant, disco).

Basado en el patron de Bulk Insert con latencia controlada.

Arquitectura:
- BatchAccumulator[T] bufferiza items con max_batch_size + max_latency_ms.
- Al cumplirse cualquiera, descarga el batch via flush().
- Backpressure si el buffer excede 2x max_batch_size.
- Thread-safe via asyncio.Queue o threading.Lock.

Referencia: arXiv:2606.01533 (MACU) â€” async I/O fusion.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class BatchStats:
    """Estadisticas de operacion del BatchAccumulator.

    Attributes:
        total_items: Items procesados desde inicio.
        total_batches: Batches descargados.
        avg_batch_size: Tamano promedio de batch.
        total_latency_ms: Latencia total acumulada.
        dropped_items: Items descartados por backpressure.
    """
    total_items: int = 0
    total_batches: int = 0
    avg_batch_size: float = 0.0
    total_latency_ms: float = 0.0
    dropped_items: int = 0


class BatchAccumulator(Generic[T]):
    """Acumulador de items para I/O batch fusionado.

    Bufferiza items hasta que se alcanza max_batch_size O max_latency_ms,
    luego ejecuta flush() ejecutando la funcion de descarga.

    Args:
        flush_fn: Funcion asincrona que procesa el batch.
            Recibe List[T] y retorna Any.
        max_batch_size: Maximo items antes de flush forzado.
        max_latency_ms: Maximo tiempo antes de flush forzado.
        name: Nombre del acumulador (para logging).

    Example:
        >>> accumulator = BatchAccumulator(
        ...     flush_fn=mi_batch_insert,
        ...     max_batch_size=10,
        ...     max_latency_ms=50,
        ...     name="vector_search",
        ... )
        >>> await accumulator.add(item1)
        >>> await accumulator.add(item2)
        >>> # Auto-flush cuando se alcanza 10 items o 50ms
        >>> stats = accumulator.stats()
    """

    def __init__(
        self,
        flush_fn: Callable[[list[T]], Any],
        max_batch_size: int = 10,
        max_latency_ms: int = 50,
        name: str = "unnamed",
    ) -> None:
        """Inicializa el acumulador batch.

        Args:
            flush_fn: Funcion que procesa el batch.
            max_batch_size: Items antes de flush (default: 10).
            max_latency_ms: Milisegundos antes de flush (default: 50).
            name: Identificador para logging.
        """
        self._flush_fn: Callable[[list[T]], Any] = flush_fn
        self._max_batch_size: int = max(max_batch_size, 1)
        self._max_latency_ms: int = max(max_latency_ms, 1)
        self._name: str = name

        self._buffer: list[T] = []
        self._lock: threading.RLock = threading.RLock()
        self._last_flush: float = time.perf_counter()
        self._closed: bool = False
        self._stats: BatchStats = BatchStats()

        # Timer para flush por tiempo
        self._timer: threading.Timer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        logger.debug(
            "[BatchAccumulator/%s] Iniciado: batch=%d, latency=%dms",
            self._name, self._max_batch_size, self._max_latency_ms,
        )

    async def add(self, item: T) -> bool:
        """Agrega un item al buffer. Dispara flush si se alcanza el limite.

        Args:
            item: Item a agregar al batch.

        Returns:
            True si se agrego, False si el buffer esta lleno (backpressure).
        """
        if self._closed:
            logger.warning("[BatchAccumulator/%s] Cerrado, descartando item", self._name)
            return False

        with self._lock:
            # Backpressure: si el buffer excede 2x max, descartar
            if len(self._buffer) >= self._max_batch_size * 2:
                self._stats.dropped_items += 1
                logger.warning(
                    "[BatchAccumulator/%s] Backpressure: %d items en buffer",
                    self._name, len(self._buffer),
                )
                return False

            self._buffer.append(item)
            self._stats.total_items += 1

            # Si alcanzamos max_batch_size, senyalizar flush fuera del lock
            should_flush: bool = len(self._buffer) >= self._max_batch_size

        if should_flush:
            await self._flush()

        return True

    async def _flush(self) -> int:
        """Descarga el buffer actual ejecutando flush_fn.

        Returns:
            Numero de items descargados.
        """
        batch: list[T] = []
        with self._lock:
            if not self._buffer:
                return 0
            batch = list(self._buffer)
            self._buffer.clear()
            self._last_flush = time.perf_counter()

        if not batch:
            return 0

        start: float = time.perf_counter()
        try:
            if asyncio.iscoroutinefunction(self._flush_fn):
                await self._flush_fn(batch)
            else:
                self._flush_fn(batch)
            elapsed_ms: float = (time.perf_counter() - start) * 1000

            with self._lock:
                self._stats.total_batches += 1
                self._stats.total_latency_ms += elapsed_ms
                n: int = len(batch)
                self._stats.avg_batch_size = (
                    (self._stats.avg_batch_size * (self._stats.total_batches - 1) + n)
                    / self._stats.total_batches
                )

            logger.debug(
                "[BatchAccumulator/%s] Flush: %d items en %.1fms",
                self._name, len(batch), elapsed_ms,
            )
            return len(batch)

        except Exception as exc:  # noqa: BLE001
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "[BatchAccumulator/%s] Error en flush (%d items, %.1fms): %s",
                self._name, len(batch), elapsed_ms, exc,
            )
            return 0

    async def flush(self) -> int:
        """Forza un flush del buffer actual.

        Returns:
            Numero de items descargados.
        """
        return await self._flush()

    async def close(self) -> int:
        """Cierra el acumulador, forzando flush final.

        Returns:
            Numero de items descargados en flush final.
        """
        self._closed = True
        remaining: int = await self._flush()
        if self._timer:
            self._timer.cancel()
        logger.info(
            "[BatchAccumulator/%s] Cerrado: %d batches, %d items, %.1fms total",
            self._name, self._stats.total_batches, self._stats.total_items,
            self._stats.total_latency_ms,
        )
        return remaining

    def stats(self) -> BatchStats:
        """Retorna estadisticas actuales del acumulador.

        Returns:
            BatchStats con metricas acumuladas.
        """
        with self._lock:
            return BatchStats(
                total_items=self._stats.total_items,
                total_batches=self._stats.total_batches,
                avg_batch_size=self._stats.avg_batch_size,
                total_latency_ms=self._stats.total_latency_ms,
                dropped_items=self._stats.dropped_items,
            )

    @property
    def buffer_size(self) -> int:
        """Retorna el tamano actual del buffer.

        Returns:
            Numero de items en buffer.
        """
        with self._lock:
            return len(self._buffer)

    @property
    def is_closed(self) -> bool:
        """Indica si el acumulador esta cerrado.

        Returns:
            True si cerrado.
        """
        return self._closed
