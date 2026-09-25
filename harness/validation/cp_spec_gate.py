"""cp_spec_gate.py — Gate de checklist pre-codigo (CPD, ADR-0080).

WHAT: Valida que un spec declare los 4 pilares ANTES de codear: edge
cases, invariantes, complejidad BigO y constraints de I/O.
WHY: CP moderno (arXiv 2506.22954): el 44% de fallos de LLMs en
competicion es design (28.6%) + boundary (15.5%) — prevenible con
checklist, no con mas iteraciones de repair.
WHERE: Spec-first (`specs/task_template.md`): sin spec completa = sin
start (SPE); el guardian lo invoca como gate T1.

Uso:
    report = check_spec({"edges": [...], "invariants": [...],
                         "complexity": "O(n)", "io_constraints": "..."})
    if not report.passed: pedir(report.missing)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Los 4 pilares del checklist (orden de verificacion).
REQUIRED_CHECKLIST: tuple[str, ...] = (
    "edges",
    "invariants",
    "complexity",
    "io_constraints",
)


@dataclass(frozen=True)
class SpecGateReport:
    """Resultado del gate de spec.

    Attributes:
        passed: True si los 4 pilares estan presentes y no vacios.
        missing: Pilares ausentes o vacios (orden del checklist).
    """

    passed: bool
    missing: tuple[str, ...]


def _has_content(value: object) -> bool:
    """True si el valor aporta contenido (no vacio/blanco).

    Args:
        value: Valor del pilar (str, lista u otro).

    Returns:
        False para None, "", blancos, listas/tuplas/dicts vacios.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return True


def check_spec(spec: dict) -> SpecGateReport:
    """Verifica los 4 pilares del checklist en un spec.

    Args:
        spec: Dict del spec (claves = pilares).

    Returns:
        SpecGateReport con pass y pilares faltantes.

    Raises:
        TypeError: Si spec no es dict (WHAT+WHY+WHERE).
    """
    if not isinstance(spec, dict):
        raise TypeError(
            f"WHAT: spec no es dict (es {type(spec).__name__}). "
            "WHY: el gate lee pilares por clave. "
            "WHERE: check_spec"
        )
    missing = tuple(p for p in REQUIRED_CHECKLIST if not _has_content(spec.get(p)))
    return SpecGateReport(passed=not missing, missing=missing)


@dataclass(frozen=True)
class ReasoningReport:
    """Resultado del 5o pilar opcional (reasoning R1 auditable).

    Attributes:
        passed: True si hay verdict + pasos numerados.
        missing: Partes ausentes ("verdict" y/o "steps").
    """

    passed: bool
    missing: tuple[str, ...] = ()


def check_reasoning(trace: str) -> ReasoningReport:
    """Valida un reasoning trace R1 (verdict + pasos numerados).

    5o pilar OPCIONAL del spec-gate (mesa: sin trace, el R1 verify/reflect
    es inauditable e irreproducible). No rompe `check_spec` (separado).

    Args:
        trace: Texto del trace (no vacio).

    Returns:
        ReasoningReport con pass y partes faltantes.

    Raises:
        ValueError: Si esta vacio (WHAT+WHY+WHERE).
    """
    if not trace.strip():
        raise ValueError(
            "WHAT: trace vacio. "
            "WHY: sin trace no hay R1 que auditar. "
            "WHERE: check_reasoning"
        )
    lowered = trace.lower()
    missing: list[str] = []
    if "verdict" not in lowered:
        missing.append("verdict")
    steps = re.findall(r"(?m)^\s*\d+[.)]\s+\S", trace)
    if len(steps) < 1:
        missing.append("steps")
    return ReasoningReport(passed=not missing, missing=tuple(missing))
