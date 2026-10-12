"""Debate Orchestrator — paquete (extraccion mecanica).

Re-exporta todos los simbolos publicos del modulo original
`debate_orchestrator.py` para mantener backward-compatibility.
"""
from .models import (
    NO_CONSENSUS_AGREEMENT_THRESHOLD,
    DebateResult,
    DebateRound,
    DebateStrategy,
    DispatchFn,
)
from .orchestrator import DebateOrchestrator

__all__ = [
    "NO_CONSENSUS_AGREEMENT_THRESHOLD",
    "DebateOrchestrator",
    "DebateResult",
    "DebateRound",
    "DebateStrategy",
    "DispatchFn",
]
