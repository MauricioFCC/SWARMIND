"""Tipos de datos y constantes para MARSScheduler.

Extraido de mars_scheduler.py para mantener el modulo principal < 900 lineas.

Incluye:
    - AgentProfile: estado y metricas de un agente registrado.
    - TaskSpec: especificacion de una tarea a planificar.
    - Assignment: resultado de una asignacion tarea-agente.
    - Constantes del modelo Q-learning y pesos de beneficio.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Constantes del modelo Q-learning
# ---------------------------------------------------------------------------

Q_LEARNING_RATE: float = 0.15        # Tasa de aprendizaje Q
Q_DISCOUNT_FACTOR: float = 0.95       # Factor de descuento
Q_INITIAL_VALUE: float = 0.5          # Valor Q inicial para pares nuevos
Q_EXPLORATION_RATE: float = 0.10      # Probabilidad de epsilon-greedy
Q_EXPLORATION_DECAY: float = 0.995    # Decaimiento de exploracion por paso

# Pesos para el calculo de beneficio neto
WEIGHT_SUCCESS_PROB: float = 0.40     # Peso de probabilidad de exito
WEIGHT_TASK_VALUE: float = 0.25       # Peso del valor intrnseco de la tarea
WEIGHT_LATENCY_PENALTY: float = 0.20  # Peso de penalizacion por latencia
WEIGHT_COST_PENALTY: float = 0.15     # Peso de penalizacion por costo

# Parametros de cola y planificacion
MAX_QUEUE_SIZE: int = 1000           # Maximo de tareas en cola
DEFAULT_TIMEOUT: float = 300.0       # Timeout por defecto (5 min)
AGING_FACTOR: float = 1.05           # Factor de prioridad por envejecimiento
AGING_INTERVAL: float = 10.0         # Segundos entre incrementos de edad
MIN_MATCH_THRESHOLD: float = 0.15    # Umbral minimo de match para asignar
CONGESTION_THRESHOLD: float = 0.80   # Umbral de carga para declarar congestion

# Dimension del vector de embedding de tarea/agente
SKILL_VECTOR_DIM: int = 8


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class AgentProfile:
    """Perfil de capacidades y rendimiento de un agente.

    Attributes:
        agent_id: Identificador unico del agente.
        skill_vector: Diccionario {skill_name: proficiency [0, 1]}.
        total_tasks: Total de tareas asignadas.
        successes: Tareas exitosas.
        failures: Tareas fallidas.
        total_latency: Suma acumulada de latencia.
        total_cost: Suma acumulada de costo.
        current_load: Carga actual (tareas activas).
        max_load: Capacidad maxima de tareas simultaneas.
        last_assigned: Timestamp de la ultima asignacion.
        enabled: Si el agente esta habilitado para recibir tareas.
    """

    agent_id: str
    skill_vector: dict[str, float] = field(default_factory=dict)
    total_tasks: int = 0
    successes: int = 0
    failures: int = 0
    total_latency: float = 0.0
    total_cost: float = 0.0
    current_load: int = 0
    max_load: int = 3
    last_assigned: float = 0.0
    enabled: bool = True


@dataclass
class TaskSpec:
    """Especificacion de una tarea para planificacion.

    Attributes:
        task_id: Identificador unico de la tarea.
        task_type: Tipo de tarea (ej: "code_gen", "test", "research").
        value: Valor/importancia de la tarea (mayor = mas critica).
        skills_needed: Diccionario {skill: minimum_proficiency}.
        estimated_duration: Duracion estimada en segundos.
        max_cost: Costo maximo permitido en tokens.
        priority: Prioridad base (mayor = mas urgente).
        deadline: Timestamp limite para completar.
        description: Descripcion textual de la tarea.
        context: Contexto adicional arbitrario.
    """

    task_id: str
    task_type: str = "generic"
    value: float = 1.0
    skills_needed: dict[str, float] = field(default_factory=dict)
    estimated_duration: float = 60.0
    max_cost: float = 1000.0
    priority: int = 0
    deadline: float | None = None
    description: str = ""
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class Assignment:
    """Resultado de la asignacion de una tarea a un agente.

    Attributes:
        task_id: ID de la tarea asignada.
        agent_id: ID del agente asignado.
        match_score: Puntaje de compatibilidad tarea-agente.
        expected_success: Probabilidad de exito esperada [0, 1].
        expected_cost: Costo esperado en tokens.
        expected_latency: Latencia esperada en segundos.
        assigned_at: Timestamp de la asignacion.
    """

    task_id: str
    agent_id: str
    match_score: float
    expected_success: float
    expected_cost: float
    expected_latency: float
    assigned_at: float = field(default_factory=time.time)
