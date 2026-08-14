"""MARSScheduler — Planificador multi-agente basado en reinforcement learning.

Asigna tareas a agentes basado en un modelo de costo-beneficio aprendido
de ejecuciones historicas. Optimiza latencia, costo y tasa de exito.

El algoritmo central es un planificador con aprendizaje por refuerzo que:
  1. Mantiene un perfil de capacidad para cada agente (skill_vector).
  2. Calcula un "task match score" entre tarea y agente usando el
     modelo Q aprendido.
  3. Selecciona la asignacion que maximiza el beneficio neto esperado
     (success_prob * value - expected_cost).
  4. Actualiza el modelo Q con cada resultado usando una variante de
     Q-learning con estado continuo (aproximacion lineal + RBF).

MARS incluye planificacion con horizonte temporal limitado, cola de
prioridades con envejecimiento (aging), y deteccion de congestion.

Basado en: MARS (ADR-0010, C26) — Metacognitive Agent Reflective
Self-improvement. Principio-based reflection + procedural reflection.
Supera multi-turn recursive con mucho menos costo.

Uso:
    scheduler = MARSScheduler()
    scheduler.register_agent("builder", skills={"code": 0.9, "design": 0.7})
    scheduler.register_agent("scientist", skills={"research": 0.95, "analysis": 0.85})

    task = {"id": "t1", "type": "implement_api", "value": 100, "skills_needed": {"code": 0.8}}
    assignment = scheduler.schedule_task(task)
    scheduler.record_outcome(assignment.task_id, assignment.agent_id,
                             success=True, latency=2.5, cost=400)

Este modulo se convirtio en paquete (regla AGR < 500 lineas/archivo):
  - ``core.py``: clase publica MARSScheduler + delegadores privados.
  - ``state_mixin.py``: mixin de estado, registro de agentes y estadisticas.
  - ``scheduling_mixin.py``: mixin de planificacion, aprendizaje y despacho.
  - ``learning.py``: funciones puras del modelo Q (matching/beneficio).

Todos los simbolos publicos del modulo original se re-exportan aqui, por lo
que los imports existentes ``from harness.orchestrator.mars_scheduler import
MARSScheduler`` siguen funcionando identicos.
"""

from __future__ import annotations

import logging

from harness.orchestrator.mars_scheduler_types import (
    AGING_FACTOR,
    CONGESTION_THRESHOLD,
    MAX_QUEUE_SIZE,
    MIN_MATCH_THRESHOLD,
    Q_DISCOUNT_FACTOR,
    Q_EXPLORATION_DECAY,
    Q_EXPLORATION_RATE,
    Q_INITIAL_VALUE,
    Q_LEARNING_RATE,
    WEIGHT_COST_PENALTY,
    WEIGHT_LATENCY_PENALTY,
    WEIGHT_SUCCESS_PROB,
    WEIGHT_TASK_VALUE,
    AgentProfile,
    Assignment,
    TaskSpec,
)

from .core import MARSScheduler

logger = logging.getLogger(__name__)

__all__ = [
    "AGING_FACTOR",
    "CONGESTION_THRESHOLD",
    "MAX_QUEUE_SIZE",
    "MIN_MATCH_THRESHOLD",
    "Q_DISCOUNT_FACTOR",
    "Q_EXPLORATION_DECAY",
    "Q_EXPLORATION_RATE",
    "Q_INITIAL_VALUE",
    "Q_LEARNING_RATE",
    "WEIGHT_COST_PENALTY",
    "WEIGHT_LATENCY_PENALTY",
    "WEIGHT_SUCCESS_PROB",
    "WEIGHT_TASK_VALUE",
    "AgentProfile",
    "Assignment",
    "MARSScheduler",
    "TaskSpec",
    "logger",
]
