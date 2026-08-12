"""Estado interno y API de registro/estadisticas de MARSScheduler.

Submodulo interno del paquete :mod:`harness.orchestrator.mars_scheduler`.

Define ``_MARSStateMixin`` con el constructor, el registro de agentes y las
consultas de estado, extraido de forma mecanica desde ``mars_scheduler.py``
(regla AGR: archivos < 500 lineas). Los cuerpos son identicos al original;
solo cambia la ubicacion fisica del codigo.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from harness.orchestrator.mars_scheduler_types import (
    AGING_FACTOR,
    MAX_QUEUE_SIZE,
    MIN_MATCH_THRESHOLD,
    Q_DISCOUNT_FACTOR,
    Q_EXPLORATION_DECAY,
    Q_EXPLORATION_RATE,
    Q_LEARNING_RATE,
    AgentProfile,
    TaskSpec,
)

logger = logging.getLogger(__name__)


class _MARSStateMixin:
    """Estado interno + API de registro y estadisticas de MARSScheduler.

    Mantiene el registro de agentes, la cola de tareas, el modelo Q y las
    estadisticas globales. Metodos publicos de consulta y registro.
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
