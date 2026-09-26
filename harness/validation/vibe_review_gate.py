"""vibe_review_gate.py — Gate anti-vibe: Deep Scan + 2o agente (ADR-0089).

WHAT: Audita un diff IA con scan de performance + seguridad y exige el
visto bueno de un SEGUNDO agente independiente antes del merge.
WHY: Vibe-reviewing (CodeRabbit): el codigo generado por IA trae 8x
fallos de performance y 2.7x de seguridad; un solo reviewer (humano o
modelo) no basta.
WHERE: Pre-merge en CI (tras lint/test) y en `parallel_executor` para
codigo generado por agentes.

Uso:
    report = vibe_review_gate(diff, perf_scan_fn, sec_scan_fn, second_agent_fn)
    if not report.passed: bloquear(report)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("harness.validation.vibe_review_gate")


@dataclass(frozen=True)
class VibeReport:
    """Reporte del gate anti-vibe.

    Attributes:
        passed: True si scans limpios + 2o agente aprueba.
        perf_findings: Hallazgos de performance (tupla).
        sec_findings: Hallazgos de seguridad (tupla).
        second_agent_approved: Veredicto del 2o agente.
    """

    passed: bool
    perf_findings: tuple[str, ...] = ()
    sec_findings: tuple[str, ...] = ()
    second_agent_approved: bool = False


def vibe_review_gate(    diff: str,
    perf_scan_fn: Callable[[str], list[str]],
    sec_scan_fn: Callable[[str], list[str]],
    second_agent_fn: Callable[[str], bool],
) -> VibeReport:
    """Aplica Deep Scan + filtro de 2o agente al diff.

    Args:
        diff: Diff a auditar (no vacio).
        perf_scan_fn: (diff) -> hallazgos de performance.
        sec_scan_fn: (diff) -> hallazgos de seguridad.
        second_agent_fn: (diff) -> True si aprueba.

    Returns:
        VibeReport (passed solo si todo limpio + aprobado).

    Raises:
        ValueError: Si el diff esta vacio (WHAT+WHY+WHERE).
    """
    if not diff.strip():
        raise ValueError(
            "WHAT: diff vacio. "
            "WHY: sin diff no hay nada que auditar. "
            "WHERE: vibe_review_gate"
        )
    perf = tuple(perf_scan_fn(diff))
    sec = tuple(sec_scan_fn(diff))
    approved = bool(second_agent_fn(diff))
    passed = not perf and not sec and approved
    if not passed:
        logger.warning(
            "vibe_review_gate: BLOQUEO (perf=%d, sec=%d, 2o=%s)",
            len(perf), len(sec), approved,
        )
    return VibeReport(
        passed=passed, perf_findings=perf,
        sec_findings=sec, second_agent_approved=approved,
    )


#: Cliches tipicos de slop generativo (delve/tapestry/landscape...).
_SLOP_CLICHES: frozenset[str] = frozenset({
    "delve", "tapestry", "landscape", "testament", "vibrant", "crucially",
    "moreover", "furthermore", "in conclusion", "game-changer",
})

#: Hedging que diluye decisiones (might/perhaps/consider...).
_SLOP_HEDGES: frozenset[str] = frozenset({
    "might", "perhaps", "possibly", "could potentially", "may",
    "consider considering", "worth considering", "it seems",
})


def slop_score(text: str) -> float:
    """Puntua genericidad/hedging de un texto (0.0 tecnico - 1.0 slop).

    WHAT: Fraccion de oraciones con cliches IA o hedging.
    WHY: Anti-slop: aceptar output generico como DONE degrada el producto;
        el score alimenta el gate (umbral sugerido: bloquear >= 0.5).
    WHERE: Salidas de contenido (docs, skills, reportes) antes de aprobar.

    Args:
        text: Texto a puntuar (vacio = 0.0).

    Returns:
        Fraccion 0..1 de oraciones con slop.
    """
    import re as _re

    sentences = [s.strip() for s in _re.split(r"[.!?]+", text) if s.strip()]
    if not sentences:
        return 0.0
    hits = 0
    for sentence in sentences:
        lowered = sentence.lower()
        if any(c in lowered for c in _SLOP_CLICHES):
            hits += 1
            continue
        if sum(1 for h in _SLOP_HEDGES if h in lowered) >= 2:
            hits += 1
    return hits / len(sentences)
