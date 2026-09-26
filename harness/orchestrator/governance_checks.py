"""governance_checks.py — 4 tests de governance bajo presion (ADR-0089).

WHAT: Checklist con los 4 tests: 1 nombre que puede pausar, decision-log,
watcher de vendor-updates, vocero de incidente.
WHY: Governance: bajo presion importan 4 cosas (pausabilidad nombrable,
trazabilidad de decisiones, vigilancia de cambios externos y voz
autorizada); sin ellas, el incidente manda.
WHERE: Revision de governance trimestral + pre-lanzamiento.

Uso:
    for name, question in governance_checklist(): responder(question)
"""

from __future__ import annotations

#: Los 4 tests de governance (orden fijo).
GOVERNANCE_TESTS: tuple[str, ...] = (
    "pausa",
    "decision-log",
    "watcher",
    "vocero",
)

_QUESTIONS: dict[str, str] = {
    "pausa": "Quien (1 solo nombre) puede pausar el sistema ahora mismo?",
    "decision-log": "Donde esta el log de decisiones con dueno y fecha?",
    "watcher": "Quien vigila los updates de vendors/modelos que nos afectan?",
    "vocero": "Quien habla si hay incidente manana?",
}


def governance_checklist() -> tuple[tuple[str, str], ...]:
    """Retorna los 4 tests con su pregunta accionable.

    Returns:
        Tupla (nombre, pregunta) en orden.
    """
    return tuple((name, _QUESTIONS[name]) for name in GOVERNANCE_TESTS)
