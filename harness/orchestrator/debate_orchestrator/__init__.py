"""Debate Orchestrator — paquete (extraccion mecanica).

Re-exporta todos los simbolos publicos del modulo original
`debate_orchestrator.py` para mantener backward-compatibility.
"""
from .models import DebateResult, DebateRound, DebateStrategy, DispatchFn
from .orchestrator import DebateOrchestrator

__all__ = [
    "DebateOrchestrator",
    "DebateResult",
    "DebateRound",
    "DebateStrategy",
    "DispatchFn",
]
