"""Planificacion y aprendizaje online de MARSScheduler.

Submodulo interno del paquete :mod:`harness.orchestrator.mars_scheduler`.

Define ``_MARSSchedulingMixin`` con ``schedule_task``, ``record_outcome``,
``dispatch_queued`` y ``_dispatch_queued``, extraidos de forma mecanica
desde ``mars_scheduler.py`` (regla AGR: archivos < 500 lineas). Los cuerpos
son identicos al original; las llamadas a helpers privados (``_compute_*``,
``_get_q_value``, etc.) se resuelven via delegadores definidos en
:mod:`harness.orchestrator.mars_scheduler.core`.
"""

from __future__ import annotations

import heapq
import logging
import random
import time

from harness.orchestrator.mars_scheduler_types import (
    CONGESTION_THRESHOLD,
    Assignment,
    TaskSpec,
)

from .state_mixin import _MARSStateMixin

logger = logging.getLogger(__name__)


class _MARSSchedulingMixin(_MARSStateMixin):
    """Planificacion, aprendizaje Q y despacho de cola de MARSScheduler."""

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
