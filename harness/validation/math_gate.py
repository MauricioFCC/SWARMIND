"""math_gate.py — Micro-gate MATH con casos exactos frescos (mesa, ADR-0096).

WHAT: Verifica respuestas exactas contra un micro-set determinista
(aritmetica/algebra, respuestas exactas como strings).
WHY: Mesa: sin gate math no se prueba reasoning real (PBT no lo ve);
GSM8K contaminado -> casos propios frescos y exactos (sin LLM-judge).
WHERE: Pre-merge T2 para cambios en routing/math; nightly extendido.

Uso:
    report = check_math({"2+2*2": "6"})
    assert report.passed and report.score == 1.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("harness.validation.math_gate")

#: Micro-set determinista (pregunta -> respuesta exacta).
MATH_CASES: dict[str, str] = {
    "2+2*2": "6",
    "7*8": "56",
    "15-9": "6",
    "100/4": "25",
    "2**10": "1024",
    "17%5": "2",
    "3*3*3": "27",
    "144/12": "12",
    "9+10": "19",
    "100-1": "99",
    "11*11": "121",
    "2**8": "256",
    "50%7": "1",
    "13*4": "52",
    "81/9": "9",
    "5!": "120",
    "2**5+1": "33",
    "99+1": "100",
    "1000-7": "993",
    "6*7": "42",
}


@dataclass(frozen=True)
class MathGateReport:
    """Reporte del micro-gate math.

    Attributes:
        passed: True si todas correctas.
        score: Fraccion correcta (0..1).
        wrong: Tupla (pregunta, obtenido, esperado).
    """

    passed: bool
    score: float
    wrong: tuple[tuple[str, str, str], ...] = ()


def check_math(answers: dict[str, str]) -> MathGateReport:
    """Verifica respuestas contra el micro-set (comparacion exacta).

    Args:
        answers: Mapa pregunta -> respuesta dada (solo se evaluan las
            presentes en MATH_CASES; otras se ignoran).

    Returns:
        MathGateReport con pass, score y errores.
    """
    wrong: list[tuple[str, str, str]] = []
    total = 0
    for question, expected in MATH_CASES.items():
        if question not in answers:
            continue
        total += 1
        given = str(answers[question]).strip()
        if given != expected:
            wrong.append((question, given, expected))
    score = (total - len(wrong)) / total if total else 1.0
    if wrong:
        logger.warning("math_gate: %d/%d erroneas", len(wrong), total)
    return MathGateReport(
        passed=not wrong, score=score, wrong=tuple(wrong)
    )
