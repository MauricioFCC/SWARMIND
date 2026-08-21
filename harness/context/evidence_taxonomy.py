"""evidence_taxonomy — Taxonomía de evidencia O/M/I/H/S/U (ADR-0054).

Disciplina zero-assumption del Coherence Atlas: todo claim se etiqueta con
su clase de evidencia y NUNCA se promociona de clase sin nueva evidencia.
"Unresolved" es una categoria estable y respetable, no un fracaso.

Escalera de fuerza::

    U (unknown) < S (speculation) < H (hypothesis) < I (inferred)
                < M (measured)  < O (observed)

Ejemplo::

    claim = Claim(text="El cache reduce latencia 38%", evidence_class=EvidenceClass.MEASURED)
    mejor = promote(claim.evidence_class, new_evidence="benchmark reproducido x3")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class EvidenceClass(IntEnum):
    """Clase de evidencia de un claim, ordenada por fuerza ascendente."""

    UNKNOWN = 0
    SPECULATION = 1
    HYPOTHESIS = 2
    INFERRED = 3
    MEASURED = 4
    OBSERVED = 5

    @property
    def code(self) -> str:
        """Codigo de una letra del Atlas (O/M/I/H/S/U)."""
        return _CODES[self]

    @property
    def label(self) -> str:
        """Etiqueta legible en espanol."""
        return _LABELS[self]


#: Mapeo clase -> codigo de una letra (fuente unica).
_CODES: dict[EvidenceClass, str] = {
    EvidenceClass.OBSERVED: "O",
    EvidenceClass.MEASURED: "M",
    EvidenceClass.INFERRED: "I",
    EvidenceClass.HYPOTHESIS: "H",
    EvidenceClass.SPECULATION: "S",
    EvidenceClass.UNKNOWN: "U",
}

#: Mapeo clase -> etiqueta legible (fuente unica).
_LABELS: dict[EvidenceClass, str] = {
    EvidenceClass.OBSERVED: "observado",
    EvidenceClass.MEASURED: "medido",
    EvidenceClass.INFERRED: "inferido",
    EvidenceClass.HYPOTHESIS: "hipotesis",
    EvidenceClass.SPECULATION: "especulacion",
    EvidenceClass.UNKNOWN: "desconocido/no resuelto",
}

#: "Unresolved" es categoria estable y respetable (regla del Atlas).
UNRESOLVED = EvidenceClass.UNKNOWN


@dataclass(frozen=True)
class Claim:
    """Claim etiquetado con su clase de evidencia.

    Args:
        text: Enunciado del claim (no vacio).
        evidence_class: Clase de evidencia actual.
        evidence_refs: Referencias que sustentan la clase actual.

    Raises:
        ValueError: si text es vacio o evidence_refs esta vacio para
            clases > UNKNOWN (fail-fast en __post_init__).
    """

    text: str
    evidence_class: EvidenceClass
    evidence_refs: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if not self.text or not self.text.strip():
            raise ValueError(
                "ValueError: el texto del claim esta vacio. WHY: un claim sin "
                "enunciado no es verificable ni etiquetable. WHERE: "
                "Claim.__post_init__ (argumento 'text')."
            )
        if self.evidence_class > EvidenceClass.UNKNOWN and not self.evidence_refs:
            raise ValueError(
                f"ValueError: claim de clase {self.evidence_class.code} sin "
                "evidence_refs. WHY: toda clase > U exige referencias que la "
                "sustenten. WHERE: Claim.__post_init__ "
                "(argumento 'evidence_refs')."
            )


def can_promote(current: EvidenceClass, target: EvidenceClass) -> bool:
    """Indica si la promocion es legal: exactamente un escalon hacia arriba.

    Args:
        current: Clase actual del claim.
        target: Clase destino.

    Returns:
        True solo si target == current + 1 (un escalon).
    """
    return target == current + 1


def promote(
    current: EvidenceClass, new_evidence: str
) -> EvidenceClass:
    """Promociona un claim UN escalon usando nueva evidencia.

    Args:
        current: Clase de evidencia actual.
        new_evidence: Descripcion de la evidencia nueva obtenida
            (no vacia; sustenta el unico escalon permitido).

    Returns:
        La clase siguiente en la escalera (nunca salta escalones).

    Raises:
        ValueError: si new_evidence esta vacia (no hay evidencia nueva) o
            si current ya esta en OBSERVED (tope de la escalera).
    """
    if not new_evidence or not new_evidence.strip():
        raise ValueError(
            "ValueError: no hay evidencia nueva que sustente la promocion. "
            "WHY: la regla del Atlas prohibe promover de clase sin nueva "
            "evidencia. WHERE: promote() (argumento 'new_evidence')."
        )
    if current >= EvidenceClass.OBSERVED:
        raise ValueError(
            f"ValueError: {current.code} ya es el tope de la escalera. WHY: "
            "no existe clase superior a observado. WHERE: promote() "
            f"(current={current.code})."
        )
    return EvidenceClass(current + 1)


def downgrade(current: EvidenceClass) -> EvidenceClass:
    """Degradar un claim un escalon (evidencia refutada o debilitada).

    Args:
        current: Clase actual.

    Returns:
        La clase anterior en la escalera (UNKNOWN si ya era el piso).
    """
    if current <= EvidenceClass.UNKNOWN:
        return EvidenceClass.UNKNOWN
    return EvidenceClass(current - 1)
