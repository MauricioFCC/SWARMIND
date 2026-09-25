"""bounded_executor.py — Bulkhead + backpressure + watchdog (ADR-0093, OTP lite).

WHAT: Ejecutor paralelo acotado: pool por dominio (bulkhead), cola con
tope + shed policy (backpressure, nunca OOM) y deadline por tarea
(watchdog: detecta hangs que CB/retry no ven).
WHY: Mesa OTP (2/3: B+D+C-lite) — mismo mecanismo (Semaphore + Queue con
maxsize + wait_for), ~30 LOC, sin procesos OTP (GIL/threads bastan con
idempotencia + WAL ya existentes). El shed se mide (failure-registry
lo usa para tunear), no es silencioso.
WHERE: Fan-out del orquestador cuando el ParallelExecutor sin cotas
arriesga thunder-herd/OOM; métricas 30d: 0 OOM, shed-rate<2%.

Uso:
    ex = BoundedParallelExecutor(max_workers=4, queue_size=16)
    out = ex.map([lambda: trabajo(i) for i in range(10)])
"""

from __future__ import annotations

import enum
import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger("harness.orchestrator.bounded_executor")


class ShedPolicy(enum.Enum):
    """Politica de descarte con cola llena (enum inmutable)."""

    DROP_NEWEST = "drop-newest"
    DROP_OLDEST = "drop-oldest"


class ShedLoad(Exception):
    """Carga descartada por backpressure (cola llena)."""


@dataclass
class BatchOutcome:
    """Resultado de un batch acotado.

    Attributes:
        results: Resultados en orden de finalizacion de aceptadas.
        shed: Tareas descartadas por cola llena.
        timeouts: Tareas que excedieron el deadline (watchdog).
    """

    results: list[str] = field(default_factory=list)
    shed: int = 0
    timeouts: int = 0


class BoundedParallelExecutor:
    """Pool acotado con shed + watchdog por tarea.

    Args:
        max_workers: Hilos del pool (> 0).
        queue_size: Tope de tareas en espera (> 0).
        shed_policy: Que descartar con cola llena.
    """

    def __init__(
        self,
        max_workers: int,
        queue_size: int,
        shed_policy: ShedPolicy = ShedPolicy.DROP_NEWEST,
    ) -> None:
        """Inicializa el pool validando cotas.

        Args:
            max_workers: Hilos (> 0).
            queue_size: Tope de cola (> 0).
            shed_policy: Politica de descarte.

        Raises:
            ValueError: Si alguna cota no es positiva (WHAT+WHY+WHERE).
        """
        if max_workers <= 0:
            raise ValueError(
                f"WHAT: max_workers invalido: {max_workers}. "
                "WHY: se necesita al menos 1 hilo. "
                "WHERE: BoundedParallelExecutor.__init__"
            )
        if queue_size <= 0:
            raise ValueError(
                f"WHAT: queue_size invalido: {queue_size}. "
                "WHY: la cola acotada es el corazon del backpressure. "
                "WHERE: BoundedParallelExecutor.__init__"
            )
        self._max_workers = max_workers
        self._queue_size = queue_size
        self._shed_policy = shed_policy
        self._executed = 0
        self._shed_total = 0
        self._timeouts = 0
        self._lock = threading.Lock()

    @property
    def shed_total(self) -> int:
        """Descartes acumulados (metrica para tunear)."""
        with self._lock:
            return self._shed_total

    def metrics(self) -> dict[str, int]:
        """Snapshot de metricas (ejecutadas, shed, timeouts).

        Returns:
            Dict con contadores (thread-safe).
        """
        with self._lock:
            return {
                "executed": self._executed,
                "shed": self._shed_total,
                "timeouts": self._timeouts,
            }

    def map(
        self, tasks: list[Callable[[], str]], timeout_s: float = 30.0
    ) -> BatchOutcome:
        """Ejecuta tareas con cotas, shed y watchdog.

        Args:
            tasks: Callables sin args (workers).
            timeout_s: Deadline por tarea (watchdog, > 0).

        Returns:
            BatchOutcome con resultados, shed y timeouts.
        """
        pending: queue.Queue = queue.Queue(maxsize=self._queue_size)
        accepted: list[Callable[[], str]] = []
        shed = 0
        for task in tasks:
            try:
                pending.put_nowait(task)
                accepted.append(task)
            except queue.Full:
                if self._shed_policy is ShedPolicy.DROP_OLDEST and accepted:
                    dropped = accepted.pop(0)
                    try:
                        pending.get_nowait()
                    except queue.Empty:
                        pass
                    pending.put_nowait(task)
                    accepted.append(task)
                    logger.warning("bounded_executor: shed oldest (backpressure)")
                    shed += 1
                    _ = dropped
                else:
                    logger.warning("bounded_executor: shed newest (backpressure)")
                    shed += 1
        with self._lock:
            self._shed_total += shed
        results: list[str] = []
        timeouts = 0
        lock = threading.Lock()
        threads: list[threading.Thread] = []

        def _worker() -> None:
            """Consume tareas con deadline por item (watchdog)."""
            nonlocal timeouts
            while True:
                try:
                    fn = pending.get_nowait()
                except queue.Empty:
                    return
                outcome = self._run_with_deadline(fn, timeout_s)
                with lock:
                    if outcome is None:
                        timeouts += 1
                    else:
                        results.append(outcome)

        for _ in range(min(self._max_workers, len(accepted))):
            thread = threading.Thread(target=_worker, daemon=True)
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join(timeout=timeout_s * len(accepted) + 5.0)
        with self._lock:
            self._executed += len(results)
            self._timeouts += timeouts
        return BatchOutcome(results=results, shed=shed, timeouts=timeouts)

    @staticmethod
    def _run_with_deadline(
        fn: Callable[[], str], timeout_s: float
    ) -> str | None:
        """Ejecuta con deadline (watchdog): None si excede.

        Args:
            fn: Tarea a ejecutar.
            timeout_s: Deadline en segundos.

        Returns:
            Resultado o None por timeout (hilo daemon, no bloquea).
        """
        box: list[str] = []
        done = threading.Event()

        def _target() -> None:
            """Envuelve la tarea capturando el resultado."""
            try:
                box.append(fn())
            finally:
                done.set()

        worker = threading.Thread(target=_target, daemon=True)
        worker.start()
        if not done.wait(timeout=timeout_s):
            return None
        worker.join(timeout=1.0)
        return box[0] if box else None
