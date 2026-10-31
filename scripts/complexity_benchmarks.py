"""Benchmarks puros por escala para el gate de complejidad (O(n²) detector).

Cada benchmark expone una funcion ``run(n)`` con coste esperado **lineal** en
``n``. El gate mide la mediana de varias repeticiones y compara el crecimiento
entre escalas (N -> 2N -> 4N); si el ratio se dispara, hay un hotspot
superlineal. Se usa tiempo de pared (no instrucciones) porque el objetivo son
funciones Python puras; el umbral es holgado para tolerar ruido de CI.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from harness.kernel import BoundedMailbox, EventLog, KernelLoop, MessageEnvelope
from harness.memory_rag.binary_tuning import OversampleTuner
from harness.memory_rag.cache_threshold import AdaptiveThreshold
from harness.memory_rag.memory_heat import heat_score
from harness.memory_rag.ruscadb_store import RuscaDBStore

#: Escalas medidas por el gate (N, 2N, 4N, 8N). Suficientemente grandes para
#: que la medición domine el ruido del scheduler (~ms por muestra).
SCALES: tuple[int, ...] = (10_000, 20_000, 40_000, 80_000)


def _bench_mailbox(n: int) -> None:
    """Encolar/desencolar n mensajes en un mailbox acotado."""
    box = BoundedMailbox(capacity=n + 1)
    for seq in range(n):
        box.put(MessageEnvelope(seq=seq, kind="bench"))
    while box.get() is not None:
        pass


def _bench_event_log(n: int) -> None:
    """Registrar n eventos en el event log (append O(1) amortizado)."""
    # Ventana acotada: mide el append, no el crecimiento de memoria del deque.
    log = EventLog(max_entries=1024, overflow="drop_oldest")
    for index in range(n):
        log.append("bench", {"i": index})


def _bench_kernel_dispatch(n: int) -> None:
    """Despachar n mensajes por el kernel (single-loop, sin spawn)."""
    loop = KernelLoop(
        BoundedMailbox(capacity=1024),
        EventLog(max_entries=1024, overflow="drop_oldest"),
    )
    loop.register("bench", lambda _payload, _env: None)
    # Lotes de 512: el buzón nunca desborda y la memoria queda acotada, así se
    # mide el coste de dispatch (no el crecimiento del allocator).
    for start in range(0, n, 512):
        for _ in range(min(512, n - start)):
            loop.submit("bench")
        loop.run()


def _bench_trust_filter(n: int) -> None:
    """Filtrar/puntuar n resultados de retrieval (gobernanza de confianza)."""
    store = RuscaDBStore.__new__(RuscaDBStore)
    items = [
        {
            "id": str(index),
            "score": 1.0 / (index + 1),
            "created_at": "2026-10-01T00:00:00+00:00",
            "metadata": {"trust_tier": "user_stated"},
        }
        for index in range(n)
    ]
    store._apply_trust_and_recency(items, top_k=n, half_life_days=30)


def _bench_heat_score(n: int) -> None:
    """Calcular heat_score para n entradas (decaimiento exponencial)."""
    import datetime as dt

    now = dt.datetime(2026, 10, 30, tzinfo=dt.UTC)
    for index in range(n):
        heat_score(index % 10, "2026-09-01T00:00:00+00:00", now, 30.0)


def _bench_adaptive_observe(n: int) -> None:
    """Actualizar el umbral adaptativo n veces (control por cubo)."""
    learner = AdaptiveThreshold(base=0.92, step=0.001)
    for index in range(n):
        learner.observe(f"prompt-{index % 50}", correct=index % 2 == 0)


def _bench_oversample_observe(n: int) -> None:
    """Actualizar el tuner de oversampling n veces (EWMA + clamp)."""
    tuner = OversampleTuner(min_oversample=1, max_oversample=8)
    for index in range(n):
        tuner.observe("bench", recall=0.5 if index % 3 == 0 else 1.0)


#: Paneles reutilizados por el benchmark de TS_RANK (construcción fuera del reloj).
_TS_RANK_PANELS: dict[int, Any] = {}


def _bench_ts_rank(n: int) -> None:
    """Rank rolling con ventana proporcional a n (Fenwick: O(n log n)).

    La ventana crece con ``n`` (``n // 10``): si alguien vuelve a la versión
    ingenua O(n·W), el ratio se dispara a ~4 y el gate falla.
    """
    import numpy as np

    from harness.alpha_mining.factor_dsl import _ts_rank

    panel = _TS_RANK_PANELS.get(n)
    if panel is None:
        panel = np.random.default_rng(7).normal(0.0, 1.0, size=(n, 1))
        _TS_RANK_PANELS[n] = panel
    _ts_rank(panel, max(2, n // 10))


#: Nombre -> (funcion, clase esperada de complejidad).
BENCHMARKS: Mapping[str, tuple[Callable[[int], Any], str]] = {
    "kernel.mailbox": (_bench_mailbox, "linear"),
    "kernel.event_log": (_bench_event_log, "linear"),
    "kernel.dispatch": (_bench_kernel_dispatch, "linear"),
    "memory.trust_filter": (_bench_trust_filter, "linear"),
    "memory.heat_score": (_bench_heat_score, "linear"),
    "cache.adaptive_observe": (_bench_adaptive_observe, "linear"),
    "bq.oversample_observe": (_bench_oversample_observe, "linear"),
    "alpha.ts_rank": (_bench_ts_rank, "n_log_n"),
}


__all__ = ["BENCHMARKS", "SCALES"]
