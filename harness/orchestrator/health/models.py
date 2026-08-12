"""Health models — constantes de umbrales y dataclass ``HealthStatus``.

Extraccion mecanica del modulo original
``harness/orchestrator/health.py`` (sin cambios de logica ni firmas).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Umbrales para deteccion de fallos cognitivos
MAX_REPEATED_SUBTASK = 3       # Misma subtask ejecutada N veces = repeater
MAX_LEVEL_DURATION_SEC = 300   # 5 minutos por nivel = timeout
MAX_STALLED_SEC = 120          # 2 minutos sin progreso = wanderer
MAX_ALTERNATIONS = 5           # Alternancias entre mismas subtasks = looper


@dataclass
class HealthStatus:
    """Resultado de un health check."""
    healthy: bool
    level: str                # liveness | readiness | cognitive
    status: str               # ok | warning | critical
    message: str
    details: dict = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "healthy": self.healthy,
            "level": self.level,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }
