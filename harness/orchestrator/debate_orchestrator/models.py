"""Modelos de datos del Debate Orchestrator (extraccion mecanica).

Contiene las estructuras de datos publicas: enum de estrategias,
dataclasses de ronda/resultado y el alias de funcion de dispatch.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DebateStrategy(str, Enum):
    """Available debate strategies for multi-agent coordination."""

    CONSENSUS = "consensus"
    """All agents produce answers independently, then vote on the best one."""

    CRITIQUE = "critique"
    """Primary agent produces an answer, secondary agent critiques, refinement."""

    DELIBERATION = "deliberation"
    """Sequential debate where each agent builds upon the previous output."""

@dataclass
class DebateRound:
    """A single round of debate with agent outputs and feedback."""

    round_num: int
    agent_outputs: dict[str, str] = field(default_factory=dict)
    critique_feedback: dict[str, str] = field(default_factory=dict)
    synthesis: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_num": self.round_num,
            "agent_outputs": dict(self.agent_outputs),
            "critique_feedback": dict(self.critique_feedback),
            "synthesis": self.synthesis,
            "confidence": self.confidence,
        }

@dataclass
class DebateResult:
    """The final result of a complete debate session."""

    session_id: str
    task: str
    strategy: DebateStrategy
    rounds: list[DebateRound] = field(default_factory=list)
    final_answer: str = ""
    confidence: float = 0.0
    agent_agreement: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task": self.task,
            "strategy": self.strategy.value if isinstance(self.strategy, DebateStrategy) else self.strategy,
            "rounds": [r.to_dict() for r in self.rounds],
            "final_answer": self.final_answer,
            "confidence": self.confidence,
            "agent_agreement": self.agent_agreement,
            "metadata": dict(self.metadata),
        }

DispatchFn = Callable[[str, str, dict[str, Any]], str]
