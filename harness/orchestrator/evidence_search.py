"""evidence_search.py — BUSEV: busqueda de evidencia con estrategias en paralelo (ADR-0087).

WHAT: Fan-out ciego 1+1 por defecto (investiga + refuta) con matriz
converge/condiciona; escala a 4 solo con contradiccion real o decision
irreversible mayor; SIFT-1 vigencia (<18m tech); claim-trace con IDs.
WHY: BUSEV (experimento 4 agentes x 4 estrategias): la triangulacion no
cambia el veredicto, lo hace desplegable; escalar a 4 siempre es waste
(topar salida a tabla 4-6 filas + veredicto 1 linea).
WHERE: Fase previa R0 de toda mesa futura; research del scientist.

Uso:
    matrix = evidence_search("SSE vs WebSocket?", strategies={...})
    matrix = evidence_search(q, strategies4, escalate=True)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("harness.orchestrator.evidence_search")


@dataclass(frozen=True)
class EvidenceRow:
    """Fila de evidencia de una estrategia.

    Attributes:
        source_id: ID trazable (p. ej. "A1", "C3").
        strategy: Nombre de la estrategia (academica/oficial/critica/comunidad).
        claim: Hallazgo en 1 linea.
        converges: True si converge con el veredicto emergente.
    """

    source_id: str
    strategy: str
    claim: str
    converges: bool


@dataclass(frozen=True)
class EvidenceMatrix:
    """Matriz converge/condiciona de la busqueda.

    Attributes:
        rows: Filas de evidencia (orden de estrategia).
        escalated: True si se escalo a 4 estrategias.
    """

    rows: tuple[EvidenceRow, ...]
    escalated: bool = False


def evidence_search(
    question: str,
    strategies: dict[str, Callable[[str], list[dict]]],
    escalate: bool = False,
) -> EvidenceMatrix:
    """Ejecuta estrategias ciegas en paralelo y arma la matriz.

    Por defecto 1+1 (las 2 primeras del dict: investiga + refuta); con
    `escalate=True` corre las 4 (contradiccion real o irreversible mayor).

    Args:
        question: Pregunta a investigar (no vacia).
        strategies: Mapa estrategia -> fn(question) -> [{id, claim,
            converges}]. Orden de insercion = orden de ejecucion.
        escalate: True para usar las 4 estrategias.

    Returns:
        EvidenceMatrix con filas y flag de escalado.

    Raises:
        ValueError: Si la pregunta esta vacia o no hay estrategias.
    """
    if not question.strip():
        raise ValueError(
            "WHAT: pregunta vacia. "
            "WHY: sin pregunta no hay ficha (sin ficha no hay busqueda). "
            "WHERE: evidence_search"
        )
    if not strategies:
        raise ValueError(
            "WHAT: sin estrategias. "
            "WHY: minimo investiga+refuta (1+1 ciegas). "
            "WHERE: evidence_search"
        )
    names = list(strategies)
    selected = names if escalated(escalate, names) else names[:2]
    rows: list[EvidenceRow] = []
    for name in selected:
        for finding in strategies[name](question):
            rows.append(EvidenceRow(
                source_id=str(finding.get("id", "?")),
                strategy=name,
                claim=str(finding.get("claim", ""))[:200],
                converges=bool(finding.get("converges", False)),
            ))
    logger.info(
        "evidence_search: %d filas de %d estrategias (escalado=%s)",
        len(rows), len(selected), escalate,
    )
    return EvidenceMatrix(rows=tuple(rows), escalated=len(selected) > 2)


def escalated(escalate: bool, names: list[str]) -> bool:
    """True si se justifica escalar a 4 estrategias.

    Args:
        escalate: Flag del caller (contradiccion o irreversible mayor).
        names: Estrategias disponibles.

    Returns:
        True si escalate y hay mas de 2 estrategias.
    """
    return bool(escalate and len(names) > 2)
