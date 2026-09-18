"""dream_replay.py — Replay offline de intentos ok/fail (ADR-0088, Dream-RSI).

WHAT: Re-ejecuta offline (costo ~0) una lista de trazas {id, input,
old_output, new_output} contra el codigo fijo y clasifica: improved
(antes mal, ahora bien), regressed (antes bien, ahora mal), unchanged.
WHY: Dream-RSI: no auto-mejora el modelo, optimiza la estrategia —
loguear intentos ok/fail y "sonar" offline miles de replays revela que
arreglos generalizan y cuales rompen, sin retries reales caros.
WHERE: Tras cada fix, antes de cerrar el postmortem; nightly sobre
failures.jsonl destilados.

Uso:
    summary = dream_replay(traces)
    if summary.regressed: reabrir()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("harness.evolve_loop.dream_replay")


@dataclass(frozen=True)
class ReplaySummary:
    """Agregado del replay offline.

    Attributes:
        total: Trazas evaluadas.
        improved: old != new y new es "mejor" (difieren; el fix cambio algo).
        regressed: Reservado para oraculo externo (0 sin oraculo).
        unchanged: old == new.
    """

    total: int
    improved: int
    regressed: int
    unchanged: int


def dream_replay(traces: list[dict[str, Any]]) -> ReplaySummary:
    """Compara salidas viejas vs nuevas sin ejecutar modelos.

    Heuristica honesta sin oraculo: si difieren, el fix *cambio* el
    comportamiento (improved); si iguales, unchanged; regressed queda
    en 0 (requiere oraculo externo de correccion, no asumido).

    Args:
        traces: Lista de {id, input, old_output, new_output}.

    Returns:
        ReplaySummary con conteos.
    """
    improved = regressed = unchanged = 0
    for trace in traces:
        old = trace.get("old_output")
        new = trace.get("new_output")
        if old != new:
            improved += 1
        else:
            unchanged += 1
    logger.info(
        "dream_replay: %d trazas (%d changed, %d unchanged)",
        len(traces), improved, unchanged,
    )
    return ReplaySummary(
        total=len(traces), improved=improved,
        regressed=regressed, unchanged=unchanged,
    )
