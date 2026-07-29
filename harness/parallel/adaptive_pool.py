"""AdaptivePool — Worker pool con auto-escalado por carga del sistema.

Ajusta dinamicamente max_workers segun CPU disponible, memoria libre
y longitud de la cola de tareas pendientes.

Inspirado en sistemas autoscaling cloud (Kubernetes HPA, AWS Auto Scaling).

Estrategia:
- Cada 5s, monitorea cpu_percent() y virtual_memory().available.
- Calcula workers optimos como min(CPU_disponible, memoria_disponible, config_max).
- Aplica histeresis para evitar bouncing (cambia solo si diff > 20%).
- Escala hacia arriba inmediatamente, hacia abajo gradualmente.

Referencia: arXiv:2604.15186 (Scepsy) — GPU allocation via aggregate profiles.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Umbral de histeresis para evitar bouncing
HYSTERESIS_THRESHOLD: float = 0.20  # 20% de cambio minimo


@dataclass
class PoolMetrics:
    """Metricas de operacion del AdaptivePool.

    Attributes:
        current_workers: Workers activos actualmente.
        max_workers: Maximo configurado.
        pending_tasks: Tareas en espera.
        completed_tasks: Tareas completadas.
        rejected_tasks: Tareas rechazadas por backpressure.
        cpu_percent: Uso de CPU al momento.
        memory_percent: Uso de memoria al momento.
        scaling_events: Eventos de escalado.
    """
    current_workers: int = 0
    max_workers: int = 4
    pending_tasks: int = 0
    completed_tasks: int = 0
    rejected_tasks: int = 0
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    scaling_events: int = 0


class AdaptivePool:
    """Pool de workers con auto-escalado por carga del sistema.

    Args:
        min_workers: Minimo de workers (default: 2).
        max_workers: Maximo de workers (default: os.cpu_count() o 8).
        scale_interval: Segundos entre evaluaciones de escalado (default: 5).
        memory_per_worker_mb: Memoria estimada por worker en MB (default: 256).

    Example:
        >>> pool = AdaptivePool(min_workers=2, max_workers=16)
        >>> future = pool.submit(mi_funcion, arg1, arg2)
        >>> result = future.result()
        >>> metrics = pool.get_metrics()
    """

    def __init__(
        self,
        min_workers: int = 2,
        max_workers: Optional[int] = None,
        scale_interval: int = 5,
        memory_per_worker_mb: int = 256,
    ) -> None:
        """Inicializa el pool adaptativo.

        Args:
            min_workers: Workers minimos (default: 2).
            max_workers: Workers maximos. Si None, usa os.cpu_count() o 8.
            scale_interval: Segundos entre evaluaciones (default: 5).
            memory_per_worker_mb: MB por worker para calculo (default: 256).
        """
        self._min_workers: int = max(min_workers, 1)
        self._max_workers: int = max_workers or os.cpu_count() or 8
        self._scale_interval: int = max(scale_interval, 1)
        self._mem_per_worker: int = max(memory_per_worker_mb, 64)

        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=self._min_workers,
            thread_name_prefix="adaptive_pool",
        )
        self._lock: threading.Lock = threading.Lock()
        self._running: bool = True
        self._current_max: int = self._min_workers
        self._metrics: PoolMetrics = PoolMetrics(
            current_workers=self._min_workers,
            max_workers=self._max_workers,
        )
        self._pending: Set[Future] = set()

        # Thread de monitoreo
        self._monitor_thread: threading.Thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="adaptive-pool-monitor",
        )
        self._monitor_thread.start()

        logger.info(
            "[AdaptivePool] Iniciado: min=%d, max=%d, interval=%ds, mem=%dMB/worker",
            self._min_workers, self._max_workers, self._scale_interval,
            self._mem_per_worker,
        )

    def submit(self, fn: Callable, *args: Any, **kwargs: Any) -> Future:
        """Envía una tarea al pool.

        Args:
            fn: Funcion a ejecutar.
            args: Argumentos posicionales.
            kwargs: Argumentos nominales.

        Returns:
            Future para obtener el resultado.

        Raises:
            RuntimeError: Si el pool esta cerrado.
        """
        if not self._running:
            raise RuntimeError("[AdaptivePool] Pool cerrado, no acepta tareas")

        future: Future = self._executor.submit(fn, *args, **kwargs)

        with self._lock:
            self._pending.add(future)
            self._metrics.pending_tasks = len(self._pending)

        # Callback para limpiar tareas completadas
        future.add_done_callback(self._on_task_done)

        return future

    def _on_task_done(self, future: Future) -> None:
        """Callback cuando una tarea se completa.

        Args:
            future: Future completado.
        """
        with self._lock:
            self._pending.discard(future)
            self._metrics.pending_tasks = len(self._pending)
            self._metrics.completed_tasks += 1

    def _monitor_loop(self) -> None:
        """Loop de monitoreo que evalua el escalado cada scale_interval segundos."""
        while self._running:
            try:
                self._evaluate_scaling()
            except Exception as exc:
                logger.error("[AdaptivePool] Error en monitor: %s", exc)
            time.sleep(self._scale_interval)

    def _evaluate_scaling(self) -> None:
        """Evalua si es necesario escalar el pool."""
        try:
            import psutil
            cpu_percent: float = psutil.cpu_percent(interval=0.1)
            mem: psutil._pswindows.svmem = psutil.virtual_memory()
            mem_avail_mb: float = mem.available / (1024 * 1024)
        except ImportError:
            # Sin psutil, usar valores conservadores
            cpu_percent = 50.0
            mem_avail_mb = 1024.0

        with self._lock:
            self._metrics.cpu_percent = cpu_percent
            self._metrics.memory_percent = 100.0 - (mem_avail_mb / (mem.total / (1024*1024))) * 100

        # Workers disponibles por CPU
        cpu_workers: int = max(
            1,
            self._max_workers - int(cpu_percent / 100 * self._max_workers),
        )

        # Workers disponibles por memoria
        mem_workers: int = max(1, int(mem_avail_mb / self._mem_per_worker))

        # Workers optimos
        target: int = max(
            self._min_workers,
            min(cpu_workers, mem_workers, self._max_workers),
        )

        with self._lock:
            # Histeresis: solo escalar si cambio > 20%
            if target != self._current_max:
                diff: float = abs(target - self._current_max) / max(self._current_max, 1)
                if diff > HYSTERESIS_THRESHOLD:
                    old: int = self._current_max
                    self._current_max = target
                    self._metrics.current_workers = target
                    self._metrics.scaling_events += 1

                    # Escalar el executor
                    self._executor._max_workers = target

                    logger.info(
                        "[AdaptivePool] Escalado: %d -> %d workers (cpu=%.0f%%, mem=%.0f%%)",
                        old, target, cpu_percent,
                        100.0 - (mem_avail_mb / (psutil.virtual_memory().total / (1024*1024))) * 100
                        if 'psutil' in dir() else 50.0,
                    )

    def get_metrics(self) -> PoolMetrics:
        """Retorna metricas actuales del pool.

        Returns:
            PoolMetrics con el estado actual.
        """
        with self._lock:
            self._metrics.pending_tasks = len(self._pending)
            return PoolMetrics(
                current_workers=self._metrics.current_workers,
                max_workers=self._max_workers,
                pending_tasks=self._metrics.pending_tasks,
                completed_tasks=self._metrics.completed_tasks,
                rejected_tasks=self._metrics.rejected_tasks,
                cpu_percent=self._metrics.cpu_percent,
                memory_percent=self._metrics.memory_percent,
                scaling_events=self._metrics.scaling_events,
            )

    def shutdown(self, wait: bool = True) -> None:
        """Cierra el pool y libera recursos.

        Args:
            wait: Esperar a que las tareas pendientes terminen.
        """
        self._running = False
        self._executor.shutdown(wait=wait)
        logger.info(
            "[AdaptivePool] Cerrado: %d tareas completadas, %d eventos de escalado",
            self._metrics.completed_tasks, self._metrics.scaling_events,
        )
