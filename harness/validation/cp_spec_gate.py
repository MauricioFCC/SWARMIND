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
