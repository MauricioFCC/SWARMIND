"""Adaptive Planning — meta-agente que ajusta la topología del plan.

Antes: harness/orchestrator/adaptive_planner.py (859 lineas).
Ahora: paquete ``harness/orchestrator/adaptive_planner/``:

- ``constants.py``: umbrales, modos de plan y fases PSMAS.
- ``models.py``: enums (PlanStrategy, AdaptationTrigger) y dataclasses
  (PlanFeedback, StrategyStats, PhasePlan).
- ``core.py``: clase ``AdaptivePlanner`` (seleccion, feedback, recomendacion).
- ``psmas.py``: mixin ``_PSMASMixin`` (phase scheduling + compresion).
- ``persistence.py``: mixin ``_PersistenceMixin`` (save/load).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original para mantener backward-compat:

    from harness.orchestrator.adaptive_planner import AdaptivePlanner

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from .constants import (
    ALWAYS_ACTIVE_AGENTS,
    MODE_HYBRID,
    MODE_PARALLEL,
    MODE_SEQUENTIAL,
    MODE_SINGLE_AGENT,
    PHASE_BUILDER,
    PHASE_GUARDIAN,
    PHASE_SCIENTIST,
    PSMAS_DEFAULT_WINDOW,
    PSMAS_MIN_AGENTS,
    REPLAN_FAILURE_RATE,
    REPLAN_MIN_SUBTASKS,
    REPLAN_STALLED_LEVELS,
)
from .core import AdaptivePlanner
from .models import (
    AdaptationTrigger,
    PhasePlan,
    PlanFeedback,
    PlanStrategy,
    StrategyStats,
)

__all__ = [
    "ALWAYS_ACTIVE_AGENTS",
    "MODE_HYBRID",
    "MODE_PARALLEL",
    "MODE_SEQUENTIAL",
    "MODE_SINGLE_AGENT",
    "PHASE_BUILDER",
    "PHASE_GUARDIAN",
    "PHASE_SCIENTIST",
    "PSMAS_DEFAULT_WINDOW",
    "PSMAS_MIN_AGENTS",
    "REPLAN_FAILURE_RATE",
    "REPLAN_MIN_SUBTASKS",
    "REPLAN_STALLED_LEVELS",
    "AdaptationTrigger",
    "AdaptivePlanner",
    "PhasePlan",
    "PlanFeedback",
    "PlanStrategy",
    "StrategyStats",
]
