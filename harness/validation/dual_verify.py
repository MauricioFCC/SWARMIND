"""dual_verify.py — Verificacion dual fast vs brute-force (CPD, ADR-0080).

WHAT: Ejecuta la solucion candidata y una referencia brute-force sobre
los mismos casos y reporta divergencias (indice + obtenido + esperado).
WHY: CP moderno (Wonda ICML 2026): sin OJ externo, la referencia
brute-force confirma correccion y complejidad; una excepcion del fast
tambien cuenta como mismatch (robustez, no solo valor).
WHERE: Guardian tras generar codigo; PBT como oraculo de propiedades;
tests de regresion de algoritmos del harness.

Uso:
    report = dual_verify(mi_sort, sorted, [[], [3, 1], [2, 2, 1]])
    assert report.passed
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("harness.validation.dual_verify")


@dataclass(frozen=True)
class DualReport:
    """Reporte de la verificacion dual.

    Attributes:
        passed: True si fast == brute en todos los casos.
        mismatches: Tupla (indice, obtenido, esperado) por divergencia.
        cases: Numero de casos evaluados.
    """

    passed: bool
    mismatches: tuple[tuple[int, Any, Any], ...]
    cases: int


def dual_verify(
    fast_fn: Callable[[Any], Any],
    brute_fn: Callable[[Any], Any],
    cases: list[Any],
) -> DualReport:
    """Compara fast vs brute-force caso por caso (sin OJ externo).

    Args:
        fast_fn: Solucion candidata (puede lanzar; cuenta como mismatch).
        brute_fn: Referencia obviamente-correcta (lenta pero simple).
        cases: Casos de entrada (incluir vacios, unitarios, duplicados).

    Returns:
        DualReport con pass, mismatches y conteo (vacio = pass vacuo).
    """
    mismatches: list[tuple[int, Any, Any]] = []
    for idx, case in enumerate(cases):
        try:
            got = fast_fn(case)
        except Exception as exc:  # noqa: BLE001 - robustez: el fallo es dato
            logger.warning("dual_verify: fast lanzo en caso %d: %s", idx, exc)
            mismatches.append((idx, f"<excepcion: {exc}>", _safe_brute(brute_fn, case)))
            continue
        expected = _safe_brute(brute_fn, case)
        if got != expected:
            mismatches.append((idx, got, expected))
    return DualReport(
        passed=not mismatches, mismatches=tuple(mismatches), cases=len(cases)
    )


def _safe_brute(brute_fn: Callable[[Any], Any], case: Any) -> Any:
    """Ejecuta la referencia capturando su excepcion como valor.

    Args:
        brute_fn: Referencia brute-force.
        case: Caso de entrada.

    Returns:
        Salida de la referencia o "<excepcion: ...>" si lanza.
    """
    try:
        return brute_fn(case)
    except Exception as exc:  # noqa: BLE001 - la referencia tambien puede fallar
        return f"<excepcion: {exc}>"
