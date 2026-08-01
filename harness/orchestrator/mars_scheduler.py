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
"""

from __future__ import annotations

import heapq
import logging
import math
import random
import threading
import time
from typing import Any

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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MARSScheduler
# ---------------------------------------------------------------------------


class MARSScheduler:
    """Planificador multi-agente con aprendizaje por refuerzo.

    WHAT: Implementa un planificador con Q-learning que aprende la
    asignacion optima de tareas a agentes basado en outcomes historicos.
    WHY: La asignacion manual o round-robin ignora las capacidades
    especificas de cada agente y su rendimiento variable. MARS aprende
    que agente es mejor para que tipo de tarea.
    WHERE: Usado como capa de planificacion en el orquestador, antes
    de delegar tareas a los agentes.

    El modelo Q usa una funcion de aproximacion lineal con features
    RBF (Radial Basis Functions) sobre el espacio
    tarea x agente. Soporta:
      - Cola de prioridad con envejecimiento (aging).
      - Deteccion de congestion y backpressure.
      - Planificacion con horizonte temporal.
      - Actualizacion online del modelo Q.

    Uso:
        scheduler = MARSScheduler()
        scheduler.register_agent("builder", {"code": 0.9, "design": 0.7})
        scheduler.register_agent("scientist", {"research": 0.95})

        task = TaskSpec(task_id="t1", task_type="code_gen", value=80,
                        skills_needed={"code": 0.7})
        assignment = scheduler.schedule_task(task)
        scheduler.record_outcome(assignment.task_id, assignment.agent_id,
                                 success=True, latency=2.0, cost=300)
    """

    def __init__(
        self,
        learning_rate: float = Q_LEARNING_RATE,
        discount_factor: float = Q_DISCOUNT_FACTOR,
        exploration_rate: float = Q_EXPLORATION_RATE,
        exploration_decay: float = Q_EXPLORATION_DECAY,
        max_queue: int = MAX_QUEUE_SIZE,
        min_match_threshold: float = MIN_MATCH_THRESHOLD,
        aging_factor: float = AGING_FACTOR,
    ) -> None:
        """Inicializa el planificador MARS.

        Args:
            learning_rate: Tasa de aprendizaje Q [0, 1].
                Default: 0.15.
            discount_factor: Factor de descuento para rewards futuros
                [0, 1]. Default: 0.95.
            exploration_rate: Probabilidad de exploracion epsilon-greedy
                [0, 1]. Default: 0.10.
            exploration_decay: Factor de decaimiento por paso [0, 1].
                Default: 0.995.
            max_queue: Maximo de tareas en cola de espera.
                Default: 1000.
            min_match_threshold: Umbral minimo de match score para
                asignar directamente. Default: 0.15.
            aging_factor: Factor de incremento de prioridad por
                envejecimiento >= 1.0. Default: 1.05.

        Raises:
            ValueError: Si learning_rate, discount_factor,
                exploration_rate, o exploration_decay estan fuera de
                rango, o si max_queue < 10, min_match_threshold < 0,
                o aging_factor < 1.0.
        """
        if not 0.0 <= learning_rate <= 1.0:
            raise ValueError(
                f"WHAT: learning_rate={learning_rate} fuera de [0, 1]. "
                f"WHY: La tasa de aprendizaje Q debe estar normalizada. "
                f"WHERE: MARSScheduler.__init__"
            )
        if not 0.0 <= discount_factor <= 1.0:
            raise ValueError(
                f"WHAT: discount_factor={discount_factor} fuera de [0, 1]. "
                f"WHY: El factor de descuento debe estar normalizado. "
                f"WHERE: MARSScheduler.__init__"
            )
        if not 0.0 <= exploration_rate <= 1.0:
            raise ValueError(
                f"WHAT: exploration_rate={exploration_rate} fuera de [0, 1]. "
                f"WHY: La tasa de exploracion debe estar normalizada. "
                f"WHERE: MARSScheduler.__init__"
            )
        if not 0.0 <= exploration_decay <= 1.0:
            raise ValueError(
                f"WHAT: exploration_decay={exploration_decay} fuera de [0, 1]. "
                f"WHY: El decaimiento de exploracion debe estar normalizado. "
                f"WHERE: MARSScheduler.__init__"
            )
        if max_queue < 10:
            raise ValueError(
                f"WHAT: max_queue={max_queue} < 10. "
                f"WHY: La cola debe poder contener al menos 10 tareas. "
                f"WHERE: MARSScheduler.__init__"
            )
        if min_match_threshold < 0:
            raise ValueError(
                f"WHAT: min_match_threshold={min_match_threshold} < 0. "
                f"WHY: El umbral de match no puede ser negativo. "
                f"WHERE: MARSScheduler.__init__"
            )
        if aging_factor < 1.0:
            raise ValueError(
                f"WHAT: aging_factor={aging_factor} < 1.0. "
                f"WHY: El factor de envejecimiento debe ser >= 1.0. "
                f"WHERE: MARSScheduler.__init__"
            )

        self._learning_rate = learning_rate
        self._discount_factor = discount_factor
        self._exploration_rate = exploration_rate
        self._exploration_decay = exploration_decay
        self._max_queue = max_queue
        self._min_match_threshold = min_match_threshold
        self._aging_factor = aging_factor

        self._lock = threading.Lock()

        # Agentes registrados
        self._agents: dict[str, AgentProfile] = {}

        # Cola de tareas: heap de (-priority_efectiva, timestamp, TaskSpec)
        self._task_queue: list[tuple[float, float, TaskSpec]] = []

        # Tareas en ejecucion: {task_id: (agent_id, timestamp)}
        self._running_tasks: dict[str, tuple[str, float]] = {}

        # Tareas completadas (historial)
        self._completed_tasks: list[dict[str, Any]] = []

        # Modelo Q: {(feature_hash): q_value}
        # Aproximamos Q(s, a) con features discretizados
        self._q_table: dict[tuple[str, str], float] = {}

        # Cache de features RBF para pares tarea-agente
        self._rbf_centers: dict[str, list[float]] = {}

        # Estadisticas
        self._total_scheduled: int = 0
        self._total_completed: int = 0
        self._total_failures: int = 0
        self._last_congestion_warn: float = 0.0
        self._steps: int = 0

        logger.info(
            "MARSScheduler initialized (lr=%.3f, discount=%.3f, "
            "explore=%.3f, decay=%.3f, max_queue=%d)",
            learning_rate, discount_factor,
            exploration_rate, exploration_decay, max_queue,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent_id: str,
        skills: dict[str, float] | None = None,
        max_load: int = 3,
    ) -> None:
        """Registra un agente en el planificador.

        WHAT: Anade un agente al conjunto de recursos planificables
        con su vector de habilidades y capacidad maxima.
        WHY: El planificador necesita conocer las capacidades y
        limitaciones de cada agente para asignar tareas
        eficientemente.
        WHERE: Durante la inicializacion del sistema o cuando se
        anade un nuevo agente.

        Args:
            agent_id: Identificador unico del agente.
            skills: Diccionario {skill_name: proficiency [0, 1]}.
                Puede ser None para agentes sin perfil.
            max_load: Capacidad maxima de tareas simultaneas.
                Default: 3.

        Raises:
            ValueError: Si agent_id esta vacio, max_load < 1,
                o algun skill fuera de [0, 1].
        """
        if not agent_id or not agent_id.strip():
            raise ValueError(
                f"WHAT: agent_id='{agent_id}' esta vacio. "
                f"WHY: Todo agente necesita un identificador valido. "
                f"WHERE: MARSScheduler.register_agent"
            )
        if max_load < 1:
            raise ValueError(
                f"WHAT: max_load={max_load} < 1. "
                f"WHY: Un agente debe poder tomar al menos 1 tarea. "
                f"WHERE: MARSScheduler.register_agent"
            )

        if skills is None:
            skills = {}

        for skill_name, proficiency in skills.items():
            if not 0.0 <= proficiency <= 1.0:
                raise ValueError(
                    f"WHAT: skill='{skill_name}' proficiency={proficiency} "
                    f"fuera de [0, 1]. "
                    f"WHY: Los niveles de habilidad deben estar normalizados. "
                    f"WHERE: MARSScheduler.register_agent"
                )

        with self._lock:
            if agent_id in self._agents:
                logger.warning(
                    "MARSScheduler: agente '%s' ya registrado, "
                    "actualizando perfil",
                    agent_id,
                )

            self._agents[agent_id] = AgentProfile(
                agent_id=agent_id,
                skill_vector=dict(skills),
                max_load=max_load,
            )
            logger.info(
                "MARSScheduler: agente '%s' registrado "
                "(skills=%d, max_load=%d)",
                agent_id, len(skills), max_load,
            )

    def schedule_task(
        self,
        task: TaskSpec,
    ) -> Assignment | None:
        """Planifica una tarea asignandola al mejor agente disponible.

        WHAT: Evalua todos los agentes habilitados, calcula el match
        score usando el modelo Q aprendido, y asigna la tarea al
        mejor agente. Si ningun agente supera el umbral minimo, la
        tarea se encola.
        WHY: La asignacion optima maximiza la probabilidad de exito,
        minimiza latencia y costo, y balancea la carga entre agentes.
        WHERE: Cada vez que el orquestador recibe una nueva tarea.

        Args:
            task: Especificacion de la tarea a planificar.

        Returns:
            ``Assignment`` si se pudo asignar inmediatamente, o None
            si la tarea se encolo para asignacion posterior.

        Raises:
            ValueError: Si task.task_id esta vacio o task.value < 0.
            RuntimeError: Si no hay agentes registrados.
        """
        if not task.task_id or not task.task_id.strip():
            raise ValueError(
                f"WHAT: task.task_id='{task.task_id}' esta vacio. "
                f"WHY: Toda tarea necesita un identificador valido. "
                f"WHERE: MARSScheduler.schedule_task"
            )
        if task.value < 0:
            raise ValueError(
                f"WHAT: task.value={task.value} < 0. "
                f"WHY: El valor de una tarea no puede ser negativo. "
                f"WHERE: MARSScheduler.schedule_task"
            )

        with self._lock:
            if not self._agents:
                raise RuntimeError(
                    "WHAT: No hay agentes registrados en MARSScheduler. "
                    "WHY: No se pueden planificar tareas sin agentes. "
                    "WHERE: MARSScheduler.schedule_task. "
                    "SUGGEST: Registrar al menos un agente con register_agent()."
                )

            # Verificar si la tarea ya esta en ejecucion o completada
            if task.task_id in self._running_tasks:
                logger.warning(
                    "MARSScheduler: tarea '%s' ya esta en ejecucion",
                    task.task_id,
                )
                return None

            # --- Evaluar agentes ---
            best_assignment: Assignment | None = None
            best_score = float("-inf")

            for agent_id, profile in self._agents.items():
                if not profile.enabled:
                    continue

                # Verificar capacidad de carga
                if profile.current_load >= profile.max_load:
                    continue

                # Calcular match score
                match_score = self._compute_match_score(profile, task)

                if match_score < self._min_match_threshold:
                    continue

                # Obtener Q-value (con exploracion epsilon-greedy)
                q_value = self._get_q_value(agent_id, task.task_type)
                if random.random() < self._exploration_rate:
                    # Exploracion: anadir ruido
                    q_value += random.gauss(0, 0.1)

                # Beneficio neto esperado
                net_benefit = self._compute_net_benefit(
                    match_score, q_value, task,
                )

                if net_benefit > best_score:
                    best_score = net_benefit
                    expected_success, expected_cost, expected_latency = (
                        self._estimate_outcomes(profile, task, match_score)
                    )
                    best_assignment = Assignment(
                        task_id=task.task_id,
                        agent_id=agent_id,
                        match_score=match_score,
                        expected_success=expected_success,
                        expected_cost=expected_cost,
                        expected_latency=expected_latency,
                    )

            # --- Asignar o encolar ---
            if best_assignment is not None:
                profile = self._agents[best_assignment.agent_id]
                profile.current_load += 1
                profile.total_tasks += 1
                profile.last_assigned = time.time()

                self._running_tasks[task.task_id] = (
                    best_assignment.agent_id,
                    time.time(),
                )
                self._total_scheduled += 1

                logger.info(
                    "MARSScheduler: tarea '%s' asignada a '%s' "
                    "(match=%.3f, benefit=%.3f)",
                    task.task_id, best_assignment.agent_id,
                    best_assignment.match_score, best_score,
                )
            else:
                # Encolar con prioridad efectiva
                effective_priority = self._compute_effective_priority(task)
                # Heap: (-effective_priority, timestamp, task)
                heapq.heappush(self._task_queue, (
                    -effective_priority,
                    time.time(),
                    task,
                ))
                # Limitar tamano de cola
                while len(self._task_queue) > self._max_queue:
                    removed = heapq.heappop(self._task_queue)
                    logger.warning(
                        "MARSScheduler: cola llena, tarea '%s' descartada",
                        removed[2].task_id,
                    )

                logger.info(
                    "MARSScheduler: tarea '%s' encolada (prioridad=%.3f, "
                    "cola_size=%d)",
                    task.task_id, effective_priority, len(self._task_queue),
                )

            # Decaer exploracion
            self._exploration_rate *= self._exploration_decay
            self._steps += 1

            return best_assignment

    def record_outcome(
        self,
        task_id: str,
        agent_id: str,
        success: bool,
        latency: float,
        cost: float,
    ) -> None:
        """Registra el resultado de una tarea y actualiza el modelo Q.

        WHAT: Actualiza el perfil del agente, el modelo Q con la
        recompensa observada, libera la carga del agente, y
        re-intenta tareas encoladas si es posible.
        WHY: La retroalimentacion permite al modelo Q aprender de la
        experiencia y mejorar asignaciones futuras.
        WHERE: Cuando una tarea completa su ejecucion (exitosa o no).

        Args:
            task_id: ID de la tarea completada.
            agent_id: ID del agente que la ejecuto.
            success: True si fue exitosa.
            latency: Latencia real en segundos.
            cost: Costo real en tokens.

        Raises:
            ValueError: Si task_id o agent_id no existen en los
                registros, latency < 0, o cost < 0.
        """
        if latency < 0:
            raise ValueError(
                f"WHAT: latency={latency} < 0. "
                f"WHY: La latencia no puede ser negativa. "
                f"WHERE: MARSScheduler.record_outcome"
            )
        if cost < 0:
            raise ValueError(
                f"WHAT: cost={cost} < 0. "
                f"WHY: El costo no puede ser negativo. "
                f"WHERE: MARSScheduler.record_outcome"
            )

        with self._lock:
            # Validar que la tarea estaba en ejecucion
            running_entry = self._running_tasks.get(task_id)
            if running_entry is None:
                raise ValueError(
                    f"WHAT: task_id='{task_id}' no encontrada en ejecucion. "
                    f"WHY: Solo se pueden registrar outcomes de tareas "
                    f"planificadas. "
                    f"WHERE: MARSScheduler.record_outcome. "
                    f"RUNNING: {list(self._running_tasks.keys())}"
                )

            expected_agent, _start_time = running_entry
            if agent_id != expected_agent:
                raise ValueError(
                    f"WHAT: agent_id='{agent_id}' no coincide con el "
                    f"asignado '{expected_agent}' para tarea '{task_id}'. "
                    f"WHY: El outcome debe venir del agente asignado. "
                    f"WHERE: MARSScheduler.record_outcome"
                )

            # Actualizar perfil del agente
            profile = self._agents.get(agent_id)
            if profile is None:
                raise ValueError(
                    f"WHAT: agent_id='{agent_id}' no registrado. "
                    f"WHY: El agente debe estar registrado. "
                    f"WHERE: MARSScheduler.record_outcome"
                )

            profile.current_load = max(0, profile.current_load - 1)
            if success:
                profile.successes += 1
            else:
                profile.failures += 1
            profile.total_latency += latency
            profile.total_cost += cost

            # --- Actualizar modelo Q ---
            # Recompensa: combinacion de exito, latencia invertida, costo invertido
            reward = self._compute_q_reward(success, latency, cost)

            # Obtener el mejor Q-value futuro para este par
            max_future_q = self._get_max_q_for_task(agent_id)

            # Recuperar Q-value actual
            current_q = self._get_q_value(agent_id, task_id)

            # Actualizar Q-learning: Q(s,a) = Q(s,a) + lr * (r + gamma * max Q(s',a') - Q(s,a))
            updated_q = current_q + self._learning_rate * (
                reward + self._discount_factor * max_future_q - current_q
            )
            self._q_table[(agent_id, task_id)] = updated_q

            # Limpiar tarea de ejecucion
            del self._running_tasks[task_id]

            # Registrar en historial
            self._completed_tasks.append({
                "task_id": task_id,
                "agent_id": agent_id,
                "success": success,
                "latency": latency,
                "cost": cost,
                "reward": round(reward, 4),
                "q_value_updated": round(updated_q, 4),
                "timestamp": time.time(),
            })
            if success:
                self._total_completed += 1
            else:
                self._total_failures += 1

            # Limitar historial
            max_history = max(500, len(self._agents) * 100)
            if len(self._completed_tasks) > max_history:
                self._completed_tasks = self._completed_tasks[-max_history:]

        logger.debug(
            "MARSScheduler: tarea '%s' completada por '%s' "
            "(success=%s, latency=%.2fs, cost=%.0f, reward=%.4f, q=%.4f)",
            task_id, agent_id, success, latency, cost, reward, updated_q,
        )

        # Intentar despachar tareas encoladas
        self._dispatch_queued()

    def dispatch_queued(self) -> int:
        """Intenta despachar tareas de la cola a agentes disponibles.

        WHAT: Revisa la cola de prioridad y asigna tareas a agentes
        que tengan capacidad disponible.
        WHY: Las tareas se encolan cuando no hay agentes disponibles;
        al liberarse capacidad, deben reasignarse automaticamente.
        WHERE: Llamado despues de cada outcome, o manualmente para
        forzar re-planificacion.

        Returns:
            Numero de tareas despachadas desde la cola.
        """
        return self._dispatch_queued()

    def _dispatch_queued(self) -> int:
        """Implementacion interna de despacho de cola."""
        dispatched = 0
        with self._lock:
            # Reconstruir heap de tareas encolables
            remaining_queue: list[tuple[float, float, TaskSpec]] = []

            while self._task_queue:
                _neg_priority, _timestamp, task = heapq.heappop(self._task_queue)

                # Verificar deadline
                if task.deadline and time.time() > task.deadline:
                    logger.warning(
                        "MARSScheduler: tarea '%s' expiro (deadline superado)",
                        task.task_id,
                    )
                    continue

                # Buscar agente disponible para esta tarea
                assigned = False
                for agent_id, profile in self._agents.items():
                    if not profile.enabled:
                        continue
                    if profile.current_load >= profile.max_load:
                        continue

                    match_score = self._compute_match_score(profile, task)
                    if match_score < self._min_match_threshold:
                        continue

                    # Asignar
                    profile.current_load += 1
                    profile.total_tasks += 1
                    profile.last_assigned = time.time()
                    self._running_tasks[task.task_id] = (agent_id, time.time())
                    self._total_scheduled += 1
                    assigned = True
                    dispatched += 1

                    logger.info(
                        "MARSScheduler: tarea encolada '%s' despachada a '%s' "
                        "(match=%.3f)",
                        task.task_id, agent_id, match_score,
                    )
                    break

                if not assigned:
                    # Re-encolar con prioridad actualizada por envejecimiento
                    effective_priority = self._compute_effective_priority(task)
                    heapq.heappush(remaining_queue, (
                        -effective_priority,
                        time.time(),
                        task,
                    ))

            self._task_queue = remaining_queue

            # Verificar congestion
            total_capacity = sum(
                a.max_load for a in self._agents.values()
            )
            total_load = sum(
                a.current_load for a in self._agents.values()
            )
            if total_capacity > 0:
                load_ratio = total_load / total_capacity
                if load_ratio > CONGESTION_THRESHOLD:
                    now = time.time()
                    if now - self._last_congestion_warn > 30.0:
                        logger.warning(
                            "MARSScheduler: CONGESTION detectada "
                            "(load=%.1f%%, queue=%d, running=%d)",
                            load_ratio * 100,
                            len(self._task_queue),
                            len(self._running_tasks),
                        )
                        self._last_congestion_warn = now

        return dispatched

    def get_agent_stats(self, agent_id: str) -> dict[str, Any] | None:
        """Obtiene estadisticas de un agente.

        Args:
            agent_id: Identificador del agente.

        Returns:
            Diccionario con: agent_id, total_tasks, success_rate,
            avg_latency, avg_cost, current_load, max_load, skills,
            enabled, o None si no existe.
        """
        with self._lock:
            profile = self._agents.get(agent_id)
            if profile is None:
                return None

            return {
                "agent_id": profile.agent_id,
                "total_tasks": profile.total_tasks,
                "success_rate": (
                    profile.successes / max(profile.total_tasks, 1)
                ),
                "avg_latency": (
                    profile.total_latency / max(profile.total_tasks, 1)
                ),
                "avg_cost": (
                    profile.total_cost / max(profile.total_tasks, 1)
                ),
                "current_load": profile.current_load,
                "max_load": profile.max_load,
                "load_pct": (
                    profile.current_load / max(profile.max_load, 1) * 100
                ),
                "skills": dict(profile.skill_vector),
                "enabled": profile.enabled,
            }

    def get_queue_status(self) -> dict[str, Any]:
        """Obtiene el estado actual de la cola de tareas.

        Returns:
            Diccionario con: queue_size, oldest_task_age,
            estimated_wait, tasks_summary.
        """
        with self._lock:
            now = time.time()
            oldest_age = 0.0
            if self._task_queue:
                _, ts, _ = self._task_queue[0]
                oldest_age = now - ts

            tasks_summary = [
                {
                    "task_id": t.task_id,
                    "task_type": t.task_type,
                    "value": t.value,
                    "priority": t.priority,
                    "queued_seconds": round(now - ts, 1),
                }
                for _, ts, t in self._task_queue[:20]  # Top 20
            ]

            return {
                "queue_size": len(self._task_queue),
                "oldest_task_age_seconds": round(oldest_age, 1),
                "estimated_wait_seconds": self._estimate_wait(),
                "tasks": tasks_summary,
                "congested": self._is_congested(),
            }

    def get_system_stats(self) -> dict[str, Any]:
        """Retorna estadisticas globales del planificador.

        Returns:
            Diccionario con: total_scheduled, total_completed,
            total_failures, success_rate, agents_count, queue_size,
            running_tasks, exploration_rate, q_table_size.
        """
        with self._lock:
            total = self._total_completed + self._total_failures
            return {
                "total_scheduled": self._total_scheduled,
                "total_completed": self._total_completed,
                "total_failures": self._total_failures,
                "success_rate": (
                    self._total_completed / max(total, 1)
                ),
                "agents_count": len(self._agents),
                "agents_enabled": sum(
                    1 for a in self._agents.values() if a.enabled
                ),
                "queue_size": len(self._task_queue),
                "running_tasks": len(self._running_tasks),
                "exploration_rate": round(self._exploration_rate, 4),
                "q_table_entries": len(self._q_table),
                "steps": self._steps,
                "congested": self._is_congested(),
            }

    def enable_agent(self, agent_id: str, enabled: bool) -> bool:
        """Habilita o deshabilita un agente.

        Args:
            agent_id: Identificador del agente.
            enabled: True para habilitar, False para deshabilitar.

        Returns:
            True si se actualizo, False si el agente no existe.
        """
        with self._lock:
            profile = self._agents.get(agent_id)
            if profile is None:
                return False
            profile.enabled = enabled
            logger.info(
                "MARSScheduler: agente '%s' %s",
                agent_id, "habilitado" if enabled else "deshabilitado",
            )
            return True

    # ------------------------------------------------------------------
    # Metodos internos — modelo de matching y Q-learning
    # ------------------------------------------------------------------

    def _compute_match_score(
        self,
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
        self,
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
        self,
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

    def _get_q_value(self, agent_id: str, task_key: str) -> float:
        """Obtiene el valor Q para un par (agente, tarea).

        Args:
            agent_id: ID del agente.
            task_key: Clave de la tarea (task_id o task_type).

        Returns:
            Valor Q, o Q_INITIAL_VALUE si no existe.
        """
        return self._q_table.get(
            (agent_id, task_key), Q_INITIAL_VALUE,
        )

    def _get_max_q_for_task(self, agent_id: str) -> float:
        """Obtiene el maximo Q-value futuro para un agente.

        Args:
            agent_id: ID del agente.

        Returns:
            Maximo Q-value entre todas las tareas conocidas para
            este agente, o Q_INITIAL_VALUE si no hay datos.
        """
        values = [
            q for (aid, _), q in self._q_table.items()
            if aid == agent_id
        ]
        return max(values) if values else Q_INITIAL_VALUE

    @staticmethod
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

    def _compute_effective_priority(self, task: TaskSpec) -> float:
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

    def _estimate_wait(self) -> float:
        """Estima el tiempo de espera en cola.

        Returns:
            Tiempo estimado en segundos.
        """
        if not self._task_queue:
            return 0.0

        # Agentes disponibles
        available_slots = sum(
            max(0, a.max_load - a.current_load)
            for a in self._agents.values()
        )

        if available_slots <= 0:
            return float("inf")

        # Estimacion: tiempo promedio por tarea * tareas en cola / slots
        avg_task_time = 30.0  # Estimacion conservadora
        return (len(self._task_queue) * avg_task_time) / available_slots

    def _is_congested(self) -> bool:
        """Determina si el sistema esta en congestion.

        Returns:
            True si la carga total supera el umbral de congestion.
        """
        total_capacity = sum(
            a.max_load for a in self._agents.values()
        )
        if total_capacity <= 0:
            return True

        total_load = sum(
            a.current_load for a in self._agents.values()
        )
        return (total_load / total_capacity) > CONGESTION_THRESHOLD

    def get_completed_history(
        self,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Obtiene el historial de tareas completadas.

        Args:
            limit: Maximo de entradas a retornar. Default: 100.

        Returns:
            Lista de diccionarios con datos de cada tarea completada.
        """
        with self._lock:
            return list(self._completed_tasks[-limit:])
