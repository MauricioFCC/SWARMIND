"""latency.py — Ventana acotada de latencias con percentiles (p50/p95/p99).

WHAT: ``LatencyWindow`` guarda las ultimas ``capacity`` muestras (ms) en una
``deque`` acotada y resume ``count/mean/p50/p95/p99/max`` por nearest-rank.
WHY: el promedio esconde la cola y el spec de rendimiento pide percentiles por
operacion. Una ventana acotada evita crecer sin limite; un lock la hace segura
ante hilos porque el store se consulta desde fan-out paralelo.
WHERE: ``RuscaDBStore.latency_stats()``; consumible por health y telemetria.

Uso:
    window = LatencyWindow(capacity=256)
    window.observe(12.5)
    window.stats()["p95"]
"""

from __future__ import annotations

import math
import threading
from collections import deque

#: Muestras retenidas por defecto: suficiente para una cola estable y barato
#: de ordenar en cada lectura.
DEFAULT_CAPACITY = 256


def _nearest_rank(sorted_values: list[float], p: float) -> float:
    """Percentil nearest-rank sobre una lista ya ordenada.

    Args:
        sorted_values: Muestras ordenadas de menor a mayor.
        p: Percentil objetivo en ``(0, 100]``.

    Returns:
        La muestra que ocupa el rango ``ceil(p/100 * n)``; ``0.0`` si no hay
        muestras.
    """
    n = len(sorted_values)
    if n == 0:
        return 0.0
    idx = max(1, math.ceil(p / 100.0 * n)) - 1
    return float(sorted_values[idx])


class LatencyWindow:
    """Ventana deslizante thread-safe con resumen por percentiles.

    Attributes:
        capacity: Numero maximo de muestras retenidas.
    """

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        """Crea una ventana vacia.

        Args:
            capacity: Muestras retenidas; se descartan las mas antiguas.

        Raises:
            ValueError: Si ``capacity`` es menor que 1.
        """
        if int(capacity) < 1:
            raise ValueError(
                f"WHAT: capacity invalida: {capacity}"
                f"WHY: la ventana necesita al menos una muestra"
                f"WHERE: LatencyWindow.__init__()"
            )
        self.capacity = int(capacity)
        self._samples: deque[float] = deque(maxlen=self.capacity)
        self._lock = threading.Lock()

    def observe(self, ms: float) -> None:
        """Registra una muestra en milisegundos.

        Ignora valores no finitos o negativos: una latencia negativa es un
        error de medicion y contaminaria los percentiles.

        Args:
            ms: Duracion medida en milisegundos.
        """
        value = float(ms)
        if not math.isfinite(value) or value < 0.0:
            return
        with self._lock:
            self._samples.append(value)

    def count(self) -> int:
        """Numero de muestras retenidas en la ventana."""
        with self._lock:
            return len(self._samples)

    def stats(self) -> dict[str, float | int]:
        """Resumen de la ventana actual.

        Returns:
            ``{count, mean, p50, p95, p99, max}``; latencias en milisegundos
            y ceros cuando la ventana esta vacia.
        """
        with self._lock:
            values = sorted(self._samples)
        n = len(values)
        if n == 0:
            return {"count": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
        return {
            "count": n,
            "mean": float(sum(values) / n),
            "p50": _nearest_rank(values, 50.0),
            "p95": _nearest_rank(values, 95.0),
            "p99": _nearest_rank(values, 99.0),
            "max": float(values[-1]),
        }


__all__ = ["DEFAULT_CAPACITY", "LatencyWindow"]
