"""Modelo Q de MARS — funciones puras de matching, beneficio y recompensa.

Submodulo interno del paquete :mod:`harness.orchestrator.mars_scheduler`.

Contiene la logica matematica del Q-learning (funciones puras sin estado),
extraida de forma mecanica desde ``mars_scheduler.py`` (regla AGR: archivos
< 500 lineas). Los metodos privados de la clase ``MARSScheduler`` delegan
en estas funciones, preservando firmas, logica y constantes originales.
"""

from __future__ import annotations

import math
import time

from harness.orchestrator.mars_scheduler_types import (
    CONGESTION_THRESHOLD,
    Q_INITIAL_VALUE,
    WEIGHT_COST_PENALTY,
    WEIGHT_LATENCY_PENALTY,
    WEIGHT_SUCCESS_PROB,
    WEIGHT_TASK_VALUE,
    AgentProfile,
    TaskSpec,
)


def _compute_match_score(
    profile: AgentProfile,
    task: TaskSpec,
) -> float:
    """Calcula el score de compatibilidad entre agente y tarea.

    Usa el producto escalar de los vectores de habilidad,
    ponderado por la importancia relativa de cada skill.

    Args:
        profile: Perfil del agente.
        task: Especificacion de la tarea.

    Returns:
        Score de match [0, 1].
    """
    if not task.skills_needed:
        return 0.5  # Match neutro si no requiere skills

    total_weight = 0.0
    weighted_sum = 0.0

    for skill_name, required_level in task.skills_needed.items():
        agent_level = profile.skill_vector.get(skill_name, 0.0)
        weight = required_level  # Mayor requerimiento = mayor peso

        # Match: si el agente tiene al menos el nivel requerido
        if agent_level >= required_level:
            skill_match = 1.0
        else:
            # Match parcial: proporcion de lo requerido
            skill_match = agent_level / max(required_level, 0.01)

        weighted_sum += weight * skill_match
        total_weight += weight

    if total_weight <= 0.0:
        return 0.5

    base_match = weighted_sum / total_weight

    # Penalizar si el agente esta sobrecargado (cerca de max_load)
    if profile.max_load > 0:
        load_ratio = profile.current_load / profile.max_load
        load_penalty = 0.2 * load_ratio
        base_match *= (1.0 - load_penalty)

    return min(max(base_match, 0.0), 1.0)


def _compute_net_benefit(
    match_score: float,
    q_value: float,
    task: TaskSpec,
) -> float:
    """Beneficio neto esperado de asignar una tarea a un agente.

    Args:
        match_score: Score de compatibilidad [0, 1].
        q_value: Valor Q aprendido [0, 1].
        task: Especificacion de la tarea.

    Returns:
        Beneficio neto escalar.
    """
    # Probabilidad de exito: promedio de match_score y q_value
    success_prob = 0.6 * match_score + 0.4 * q_value

    # Valor normalizado de la tarea
    norm_value = min(task.value / 100.0, 1.0)

    # Costo esperado (inverso normalizado)
    cost_penalty = 1.0 - min(task.max_cost / 5000.0, 1.0)

    # Latencia esperada (inverso normalizado)
    latency_penalty = 1.0 - min(
        task.estimated_duration / 300.0, 1.0,
    )

    benefit = (
        WEIGHT_SUCCESS_PROB * success_prob
        + WEIGHT_TASK_VALUE * norm_value
        + WEIGHT_COST_PENALTY * cost_penalty
        + WEIGHT_LATENCY_PENALTY * latency_penalty
    )

    return benefit


def _estimate_outcomes(
    profile: AgentProfile,
    task: TaskSpec,
    match_score: float,
) -> tuple[float, float, float]:
    """Estima probabilidad de exito, costo y latencia esperados.

    Args:
        profile: Perfil del agente.
        task: Especificacion de la tarea.
        match_score: Score de compatibilidad.

    Returns:
        Tupla (expected_success, expected_cost, expected_latency).
    """
    # Exito esperado basado en historial del agente y match
    historical_rate = (
        profile.successes / max(profile.total_tasks, 1)
    )
    expected_success = 0.7 * match_score + 0.3 * historical_rate

    # Costo esperado: promedio historico + sesgo por skills
    avg_cost = (
        profile.total_cost / max(profile.total_tasks, 1)
    )
    if profile.total_tasks == 0:
        avg_cost = task.max_cost * 0.5
    expected_cost = min(avg_cost, task.max_cost * 1.5)

    # Latencia esperada
    avg_latency = (
        profile.total_latency / max(profile.total_tasks, 1)
    )
    if profile.total_tasks == 0:
        avg_latency = task.estimated_duration
    expected_latency = avg_latency

    return (expected_success, expected_cost, expected_latency)


def _get_q_value(
    q_table: dict[tuple[str, str], float],
    agent_id: str,
    task_key: str,
) -> float:
    """Obtiene el valor Q para un par (agente, tarea).

    Args:
        q_table: Tabla Q {(agent_id, task_key): valor}.
        agent_id: ID del agente.
        task_key: Clave de la tarea (task_id o task_type).

    Returns:
        Valor Q, o Q_INITIAL_VALUE si no existe.
    """
    return q_table.get(
        (agent_id, task_key), Q_INITIAL_VALUE,
    )


def _get_max_q_for_task(
    q_table: dict[tuple[str, str], float],
    agent_id: str,
) -> float:
    """Obtiene el maximo Q-value futuro para un agente.

    Args:
        q_table: Tabla Q {(agent_id, task_key): valor}.
        agent_id: ID del agente.

    Returns:
        Maximo Q-value entre todas las tareas conocidas para
        este agente, o Q_INITIAL_VALUE si no hay datos.
    """
    values = [
        q for (aid, _), q in q_table.items()
        if aid == agent_id
    ]
    return max(values) if values else Q_INITIAL_VALUE


def _compute_q_reward(
    success: bool,
    latency: float,
    cost: float,
) -> float:
    """Calcula la recompensa Q a partir del resultado.

    Args:
        success: Si la ejecucion fue exitosa.
        latency: Latencia en segundos.
        cost: Costo en tokens.

    Returns:
        Recompensa en [0, 1].
    """
    success_term = 1.0 if success else 0.0
    latency_term = math.exp(-latency / 10.0)
    cost_term = math.exp(-cost / 500.0)

    return 0.5 * success_term + 0.25 * latency_term + 0.25 * cost_term


def _compute_effective_priority(task: TaskSpec) -> float:
    """Calcula la prioridad efectiva considerando envejecimiento.

    Args:
        task: Especificacion de la tarea.

    Returns:
        Prioridad efectiva (mayor = mas urgente).
    """
    base = float(task.priority) + 1.0

    # Si tiene deadline, urgencia basada en tiempo restante
    if task.deadline:
        remaining = task.deadline - time.time()
        if remaining > 0:
            urgency = max(0.1, 1.0 / remaining) * 10
            base += urgency

    return base


def _estimate_wait(
    task_queue: list[tuple[float, float, TaskSpec]],
    agents: dict[str, AgentProfile],
) -> float:
    """Estima el tiempo de espera en cola.

    Args:
        task_queue: Cola de prioridad de tareas encoladas.
        agents: Agentes registrados en el planificador.

    Returns:
        Tiempo estimado en segundos.
    """
    if not task_queue:
        return 0.0

    # Agentes disponibles
    available_slots = sum(
        max(0, a.max_load - a.current_load)
        for a in agents.values()
    )

    if available_slots <= 0:
        return float("inf")

    # Estimacion: tiempo promedio por tarea * tareas en cola / slots
    avg_task_time = 30.0  # Estimacion conservadora
    return (len(task_queue) * avg_task_time) / available_slots


def _is_congested(agents: dict[str, AgentProfile]) -> bool:
    """Determina si el sistema esta en congestion.

    Args:
        agents: Agentes registrados en el planificador.

    Returns:
        True si la carga total supera el umbral de congestion.
    """
    total_capacity = sum(
        a.max_load for a in agents.values()
    )
    if total_capacity <= 0:
        return True

    total_load = sum(
        a.current_load for a in agents.values()
    )
    return (total_load / total_capacity) > CONGESTION_THRESHOLD
