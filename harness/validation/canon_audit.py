"""canon_audit.py — Triple audit supply-chain de URLs del canon (ADR-0089).

WHAT: Verifica cada URL del canon PEC: esquema https + status HTTP 200
(viva). Reporta las muertas para curar el canon.
WHY: AI First triple audit (GenTrust/Socket/Snyk en Skills.sh): las
dependencias (incluidas URLs de referencia) se auditan; un canon con
links rotos degrada la skill que lo cita.
WHERE: Revision trimestral del registry + pre-commit de skills.

Uso:
    report = audit_urls(urls, status_fn)  # status_fn(url) -> int
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("harness.validation.canon_audit")


@dataclass(frozen=True)
class CanonReport:
    """Reporte de auditoria del canon.

    Attributes:
        passed: True si todas vivas y https.
        dead: URLs muertas o no-https (tupla).
    """

    passed: bool
    dead: tuple[str, ...] = ()


def audit_urls(
    urls: list[str], status_fn: Callable[[str], int]
) -> CanonReport:
    """Audita URLs: https + status 200.

    Args:
        urls: URLs a verificar (no vacia).
        status_fn: (url) -> codigo HTTP (inyectable, sin red en tests).

    Returns:
        CanonReport con las muertas listadas.

    Raises:
        ValueError: Si la lista esta vacia (WHAT+WHY+WHERE).
    """
    if not urls:
        raise ValueError(
            "WHAT: lista de URLs vacia. "
            "WHY: sin URLs no hay canon que auditar. "
            "WHERE: audit_urls"
        )
    dead: list[str] = []
    for url in urls:
        if not url.lower().startswith("https://"):
            dead.append(url)
            continue
        try:
            code = status_fn(url)
        except Exception as exc:  # noqa: BLE001 - red caida = muerta
            logger.warning("canon_audit: %s sin respuesta (%s)", url, exc)
            dead.append(url)
            continue
        if code != 200:
            dead.append(url)
    if dead:
        logger.warning("canon_audit: %d URLs muertas: %s", len(dead), dead)
    return CanonReport(passed=not dead, dead=tuple(dead))
