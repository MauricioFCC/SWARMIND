"""Debate Orchestrator — paquete (extraccion mecanica).

Re-exporta todos los simbolos publicos del modulo original
`debate_orchestrator.py` para mantener backward-compatibility.
"""
from .models import (
    CONVERGENCE_THRESHOLD,
    DEFAULT_CONSENSUS_CONFIDENCE,
    NO_CONSENSUS_AGREEMENT_THRESHOLD,
    DebateResult,
    DebateRound,
    DebateStrategy,
    DispatchFn,
)
from .orchestrator import DebateOrchestrator

__all__ = [
    "CONVERGENCE_THRESHOLD",
    "DEFAULT_CONSENSUS_CONFIDENCE",
    "NO_CONSENSUS_AGREEMENT_THRESHOLD",
    "DebateOrchestrator",
    "DebateResult",
    "DebateRound",
    "DebateStrategy",
    "DispatchFn",
]
