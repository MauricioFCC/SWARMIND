"""Agent Health Check — 3 niveles de verificacion para sistemas multi-agente.

Antes: harness/orchestrator/health.py (575 lineas).
Ahora: paquete ``harness/orchestrator/health/``:

- ``models.py``: constantes MAX_* y dataclass ``HealthStatus``.
- ``cognitive.py``: clase ``CognitiveState`` (tracking de progreso).
- ``checks_mixin.py``: mixin ``_ChecksMixin`` (liveness/readiness).
- ``cognitive_mixin.py``: mixin ``_CognitiveMixin`` (cognitive + gestion de sesiones).
- ``core.py``: clase ``AgentHealthChecker`` (estado + get_hardware_info).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original para mantener backward-compat:

    from harness.orchestrator.health import AgentHealthChecker
    from orchestrator.health import CognitiveState

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""
from __future__ import annotations

from .cognitive import CognitiveState
from .cognitive_mixin import _CognitiveMixin as _CognitiveMixin
from .core import AgentHealthChecker
from .models import (
    MAX_ALTERNATIONS,
    MAX_LEVEL_DURATION_SEC,
    MAX_REPEATED_SUBTASK,
    MAX_STALLED_SEC,
    HealthStatus,
)

__all__ = [
    "MAX_ALTERNATIONS",
    "MAX_LEVEL_DURATION_SEC",
    "MAX_REPEATED_SUBTASK",
    "MAX_STALLED_SEC",
    "AgentHealthChecker",
    "CognitiveState",
    "HealthStatus",
]
