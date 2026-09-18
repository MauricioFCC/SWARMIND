"""antivenom_filter.py — Filtro antiveneno 4 cortes (ADR-0087, BUSEV).

WHAT: Valida una fuente contra 4 cortes: V1 spam/autoridad lateral (sin
metodo), V2 vigencia tech >18m, V3 vendor sin metodo reproducible, V4 sin
venue verificable. Solo PASS entra al veredicto.
WHY: Corpus-trampa BUSEV: cada newcomer debe cazar 4/4 antes de firmar
actas; un veneno en el veredicto contamina la decision entera.
WHERE: Antes de que cualquier claim entre a EvidenceMatrix o a skills.

Uso:
    verdict = antivenom_check(url, has_method=True, months_old=3,
                              is_vendor=False, venue="arXiv")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("harness.validation.antivenom_filter")

#: Vigencia maxima en tech (meses) antes de revalidar.
TECH_FRESH_MONTHS = 18


@dataclass(frozen=True)
class SourceVerdict:
    """Veredicto sobre una fuente.

    Attributes:
        passed: True si supera los 4 cortes.
        failed_cut: Corte que fallo ("V1".."V4", "" si paso).
        reason: Justificacion en 1 linea.
    """

    passed: bool
    failed_cut: str = ""
    reason: str = ""


def antivenom_check(
    url: str,
    has_method: bool,
    months_old: int,
    is_vendor: bool,
    venue: str | None,
) -> SourceVerdict:
    """Aplica los 4 cortes en orden (primero que falla, descarta).

    Args:
        url: URL de la fuente.
        has_method: True si trae metodo/dataset replicable.
        months_old: Antiguedad en meses.
        is_vendor: True si es comparativa de vendor.
        venue: Venue (arXiv/ACL/blog/...) o None si no verificable.

    Returns:
        SourceVerdict con pass/fallo y justificacion.
    """
    if not has_method:
        if is_vendor:
            return _fail("V3", url, "vendor sin metodo reproducible: direccion si, cifra no")
        return _fail("V1", url, "sin metodo ni autoridad lateral: spam/autoridad no verificada")
    if months_old > TECH_FRESH_MONTHS:
        return _fail(
            "V2", url,
            f"vigencia: {months_old}m > {TECH_FRESH_MONTHS}m en tech; revalidar o marcar NO-VERIFICADO",
        )
    if venue is None:
        return _fail("V4", url, "sin venue verificable ni trazado a primaria: no entra al veredicto")
    return SourceVerdict(passed=True, reason=f"fuente limpia: {url}")


def _fail(cut: str, url: str, reason: str) -> SourceVerdict:
    """Construye un veredicto de fallo con log.

    Args:
        cut: Corte ("V1".."V4").
        url: URL evaluada.
        reason: Justificacion.

    Returns:
        SourceVerdict con passed=False.
    """
    logger.info("antivenom_filter: %s descarta %s (%s)", cut, url, reason)
    return SourceVerdict(passed=False, failed_cut=cut, reason=reason)
