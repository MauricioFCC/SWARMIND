"""dual_verify.py — Verificacion dual fast vs brute-force (CPD, ADR-0080/0095).

WHAT: Ejecuta la solucion candidata y una referencia brute-force sobre
los mismos casos y reporta divergencias (indice + obtenido + esperado).
WHY: CP moderno (Wonda ICML 2026): sin OJ externo, la referencia
brute-force confirma correccion y complejidad; una excepcion del fast
tambien cuenta como mismatch (robustez, no solo valor). Prohibido CoT
libre como oraculo: solo ejecucion contra referencia (CoT zero-shot
-9.2pp AC en GPT-4o).
WHERE: Guardian tras generar codigo; PBT como oraculo de propiedades;
tests de regresion de algoritmos del harness.

Uso:
    report = dual_verify(mi_sort, sorted, [[], [3, 1], [2, 2, 1]])
    assert report.passed
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("harness.validation.dual_verify")

#: Dias maximos de vigencia de un set de casos (LiveCodeBench:
#: contamination-free estructural via rolling + delayed-release).
CASE_FRESHNESS_DAYS = 540


@dataclass(frozen=True)
class DualReport:
    """Reporte de la verificacion dual.

    Attributes:
        passed: True si fast == brute en todos los casos.
        mismatches: Tupla (indice, obtenido, esperado) por divergencia.
        cases: Numero de casos evaluados.
        stale: True si el set supera la vigencia (contaminacion posible).
    """

    passed: bool
    mismatches: tuple[tuple[int, Any, Any], ...]
    cases: int
    stale: bool = False


def dual_verify(
    fast_fn: Callable[[Any], Any],
    brute_fn: Callable[[Any], Any],
    cases: list[Any],
    as_of: str | None = None,
    freshness_days: int = CASE_FRESHNESS_DAYS,
    timeout_s: float | None = None,
) -> DualReport:
    """Compara fast vs brute-force caso por caso (sin OJ externo).

    Args:
        fast_fn: Solucion candidata (puede lanzar; cuenta como mismatch).
        brute_fn: Referencia obviamente-correcta (lenta pero simple).
        cases: Casos de entrada (incluir vacios, unitarios, duplicados).
        as_of: Fecha ISO del set de casos (None = sin control de vigencia).
        freshness_days: Vigencia maxima en dias (default 540).
        timeout_s: Timeout por llamada (None = sin limite; recomendado en
            prod: lo primero que rompe es un brute colgado).

    Returns:
        DualReport con pass, mismatches, conteo y flag stale.
    """
    mismatches: list[tuple[int, Any, Any]] = []
    for idx, case in enumerate(cases):
        try:
            got = _call_with_timeout(fast_fn, case, timeout_s)
        except Exception as exc:  # noqa: BLE001 - robustez: el fallo es dato
            logger.warning("dual_verify: fast lanzo en caso %d: %s", idx, exc)
            mismatches.append((idx, f"<excepcion: {exc}>", _safe_brute(brute_fn, case, timeout_s)))
            continue
        expected = _safe_brute(brute_fn, case, timeout_s)
        if got != expected:
            mismatches.append((idx, got, expected))
    return DualReport(
        passed=not mismatches, mismatches=tuple(mismatches), cases=len(cases),
        stale=_is_stale(as_of, freshness_days),
    )


def _call_with_timeout(
    fn: Callable[[Any], Any], case: Any, timeout_s: float | None
) -> Any:
    """Ejecuta con timeout opcional (anti-hang de la mesa).

    Args:
        fn: Callable a ejecutar.
        case: Entrada.
        timeout_s: Segundos (None = directo, compat).

    Returns:
        Salida de fn.

    Raises:
        TimeoutError: Si excede el timeout (con mensaje con "timeout").
        Exception: La que lance fn.
    """
    if timeout_s is None:
        return fn(case)
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(fn, case)
        try:
            return future.result(timeout=timeout_s)
        except TimeoutError as exc:
            raise TimeoutError(f"timeout tras {timeout_s}s en caso") from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _is_stale(as_of: str | None, freshness_days: int) -> bool:
    """True si el set supera la vigencia (posible contaminacion).

    Args:
        as_of: Fecha ISO del set (None = sin control -> no stale).
        freshness_days: Vigencia maxima.

    Returns:
        True si (hoy - as_of) > freshness_days; False si es invalida.
    """
    if not as_of:
        return False
    try:
        born = datetime.date.fromisoformat(as_of)
    except ValueError:
        return False
    today = datetime.datetime.now(datetime.UTC).date()
    return (today - born).days > freshness_days


def _safe_brute(
    brute_fn: Callable[[Any], Any], case: Any, timeout_s: float | None = None
) -> Any:
    """Ejecuta la referencia capturando su excepcion como valor.

    Args:
        brute_fn: Referencia brute-force.
        case: Caso de entrada.
        timeout_s: Timeout opcional (anti-hang).

    Returns:
        Salida de la referencia o "<excepcion: ...>" si lanza.
    """
    try:
        return _call_with_timeout(brute_fn, case, timeout_s)
    except Exception as exc:  # noqa: BLE001 - la referencia tambien puede fallar
        return f"<excepcion: {exc}>"
