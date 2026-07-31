"""
Paquete de workflows de orquestacion: DAG TDD estricto (ADR-0033).

Spec-First, Code-Second: los tests son la ley y el codigo del agente es
desechable. El DAG bloquea la escritura en src/ hasta que los tests sean
auditados y aprobados.
"""

from __future__ import annotations

from harness.orchestrator.workflows.tdd_strict import (
    TDDGate,
    TDDLevel,
    TDDPhase,
    TDDStrictDAG,
    TestConfidenceReport,
    build_tdd_dag,
)

__all__ = [
    "TDDGate",
    "TDDLevel",
    "TDDPhase",
    "TDDStrictDAG",
    "TestConfidenceReport",
    "build_tdd_dag",
]
