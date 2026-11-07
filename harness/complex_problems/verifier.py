"""Verificador formal inyectado + integridad del statement (ciclo 11.17).

WHAT: protocolo de verificacion formal inyectado por DI (AlphaProof,
Nature 2025-11: el verificador Lean es el ground truth — el loop NUNCA
auto-certifica) + test de lemmas anti-malformalizacion (AlphaProof Nexus,
arXiv 2605.22763): antes de contar un problema como resuelto, el enunciado
formal debe contener los marcadores requeridos del problema real.

WHY: sin verificador inyectado el loop cree pruebas de si mismo (epistemic
closure); sin anti-malformalizacion, un generador puede debilitar el
teorema y reportar falso-exito.

WHERE: ``harness/complex_problems/verifier.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class VerificationResult:
    """Resultado de una verificacion formal (frozen: inmutable)."""

    verified: bool
    trace: tuple[str, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        """Truthiness = verified (``if result:`` significa 'esta probado')."""
        return self.verified


@runtime_checkable
class Verifier(Protocol):
    """Contrato duck-typed del verificador formal (DI, sin clase concreta)."""

    def verify(self, candidate: str) -> VerificationResult:
        """Certifica o rechaza ``candidate`` contra el enunciado formal."""
        ...


def check_statement_integrity(
    statement: str, required_markers: Sequence[str]
) -> tuple[str, ...]:
    """Anti-malformalizacion: marcadores faltantes del statement formal.

    Args:
        statement: Enunciado formal del problema.
        required_markers: Substrings que el statement real debe contener
            (nombres de teoremas, tipos, hipotesis); duplicados se
            deduplican preservando el primer orden.

    Returns:
        Tupla de marcadores ausentes (vacia = integridad OK).

    Raises:
        ValueError: Si algun marcador es la cadena vacia (configuracion
            del caller bugueada; no se puede evaluar '' in statement).
    """
    missing: list[str] = []
    seen: set[str] = set()
    for marker in required_markers:
        if not marker:
            raise ValueError(
                "WHAT: marcador requerido vacio. WHY: '' esta en todo "
                "string y invalidaria el gate. WHERE: check_statement_integrity."
            )
        if marker in seen:
            continue
        seen.add(marker)
        if marker not in statement:
            missing.append(marker)
    return tuple(missing)
