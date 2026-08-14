"""Modelos del AdaptivePlanner — enums y dataclasses.

Extraidos tal cual del modulo original
``harness/orchestrator/adaptive_planner.py`` (sin cambios de logica
ni firmas).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from .constants import PSMAS_DEFAULT_WINDOW

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PlanStrategy(str, Enum):
    """Estrategia de planificación disponible."""
    SINGLE_AGENT = "single_agent"     # 1 agente hace todo
    SEQUENTIAL = "sequential"          # Pasos lineales
    FAN_OUT_FAN_IN = "fan_out_fan_in" # Paralelo → consolidar
    HYBRID = "hybrid"                 # Mezcla adaptativa


class AdaptationTrigger(str, Enum):
    """Razón por la que se gatilló una adaptación."""
    HIGH_FAILURE_RATE = "high_failure_rate"
    STALLED_PROGRESS = "stalled_progress"
    LEVEL_TIMEOUT = "level_timeout"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    REPEATER_DETECTED = "repeater_detected"
    LOOPER_DETECTED = "looper_detected"
    MANUAL_OVERRIDE = "manual_override"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PlanFeedback:
    """Feedback de una ejecución de plan."""
    session_id: str
    task_hash: str                # Hash del mensaje original
    task_type: str                # deploy | implement | research | etc
    strategy_used: PlanStrategy
    subtask_count: int
    level_count: int
    success_count: int
    failure_count: int
    total_duration_ms: float
    success_rate: float
    adaptation_triggered: bool = False
    adaptation_reason: str = ""
    metadata: dict = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "task_hash": self.task_hash,
            "task_type": self.task_type,
            "strategy_used": self.strategy_used.value,
            "subtask_count": self.subtask_count,
            "level_count": self.level_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "success_rate": round(self.success_rate, 4),
            "adaptation_triggered": self.adaptation_triggered,
            "adaptation_reason": self.adaptation_reason,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass
class StrategyStats:
    """Estadísticas de una estrategia de plan."""
    strategy: PlanStrategy
    total_uses: int = 0
    total_successes: int = 0
    total_failures: int = 0
    avg_duration_ms: float = 0.0
    avg_success_rate: float = 0.0
    last_used: str = ""

    @property
    def success_rate(self) -> float:
        return (
            self.total_successes / self.total_uses
            if self.total_uses > 0 else 0.0
        )

    def update(self, feedback: PlanFeedback) -> None:
        """Actualiza estadísticas con un feedback."""
        self.total_uses += 1
        if feedback.success_rate >= 0.7:
            self.total_successes += 1
        else:
            self.total_failures += 1

        # Running average
        self.avg_duration_ms = (
            (self.avg_duration_ms * (self.total_uses - 1) + feedback.total_duration_ms)
            / self.total_uses
        )
        self.avg_success_rate = (
            (self.avg_success_rate * (self.total_uses - 1) + feedback.success_rate)
            / self.total_uses
        )
        self.last_used = feedback.timestamp

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy.value,
            "total_uses": self.total_uses,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "avg_success_rate": round(self.avg_success_rate, 4),
            "success_rate": round(self.success_rate, 4),
            "last_used": self.last_used,
        }


@dataclass
class PhasePlan:
    """
    Plan de fases PSMAS para un conjunto de agentes.

    Almacena la asignación de fase angular por agente y el tipo de tarea
    para el cual fue generado el plan.
    """
    agent_phases: dict[str, float] = field(default_factory=dict)
    task_type: str = ""
    window_degrees: float = PSMAS_DEFAULT_WINDOW
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "agent_phases": dict(self.agent_phases),
            "task_type": self.task_type,
            "window_degrees": self.window_degrees,
            "created_at": self.created_at,
        }
