"""MARSScheduler — clase publica del planificador MARS (ensamblaje final).

Submodulo del paquete :mod:`harness.orchestrator.mars_scheduler`.

Ensambla los mixins internos (estado + planificacion) con los delegadores
de las funciones puras de Q-learning definidas en
:mod:`harness.orchestrator.mars_scheduler.learning`. Los delegadores
conservan las firmas y docstrings semanticos del original, de modo que
cualquier llamada a metodos privados existentes sigue funcionando identica.
"""

from __future__ import annotations

from harness.orchestrator.mars_scheduler_types import (
    AgentProfile,
    TaskSpec,
)

from . import learning
from .scheduling_mixin import _MARSSchedulingMixin


class MARSScheduler(_MARSSchedulingMixin):
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

    def _compute_match_score(
        self,
        profile: AgentProfile,
        task: TaskSpec,
    ) -> float:
        """Calcula el score de compatibilidad entre agente y tarea.

        Delegador de
        :func:`harness.orchestrator.mars_scheduler.learning._compute_match_score`.

        Args:
            profile: Perfil del agente.
            task: Especificacion de la tarea.

        Returns:
            Score de match [0, 1].
        """
        return learning._compute_match_score(profile, task)

    def _compute_net_benefit(
        self,
        match_score: float,
        q_value: float,
        task: TaskSpec,
    ) -> float:
        """Beneficio neto esperado de asignar una tarea a un agente.

        Delegador de
        :func:`harness.orchestrator.mars_scheduler.learning._compute_net_benefit`.

        Args:
            match_score: Score de compatibilidad [0, 1].
            q_value: Valor Q aprendido [0, 1].
            task: Especificacion de la tarea.

        Returns:
            Beneficio neto escalar.
        """
        return learning._compute_net_benefit(match_score, q_value, task)

    def _estimate_outcomes(
        self,
        profile: AgentProfile,
        task: TaskSpec,
        match_score: float,
    ) -> tuple[float, float, float]:
        """Estima probabilidad de exito, costo y latencia esperados.

        Delegador de
        :func:`harness.orchestrator.mars_scheduler.learning._estimate_outcomes`.

        Args:
            profile: Perfil del agente.
            task: Especificacion de la tarea.
            match_score: Score de compatibilidad.

        Returns:
            Tupla (expected_success, expected_cost, expected_latency).
        """
        return learning._estimate_outcomes(profile, task, match_score)

    def _get_q_value(self, agent_id: str, task_key: str) -> float:
        """Obtiene el valor Q para un par (agente, tarea).

        Delegador de
        :func:`harness.orchestrator.mars_scheduler.learning._get_q_value`.

        Args:
            agent_id: ID del agente.
            task_key: Clave de la tarea (task_id o task_type).

        Returns:
            Valor Q, o Q_INITIAL_VALUE si no existe.
        """
        return learning._get_q_value(self._q_table, agent_id, task_key)

    def _get_max_q_for_task(self, agent_id: str) -> float:
        """Obtiene el maximo Q-value futuro para un agente.

        Delegador de
        :func:`harness.orchestrator.mars_scheduler.learning._get_max_q_for_task`.

        Args:
            agent_id: ID del agente.

        Returns:
            Maximo Q-value entre todas las tareas conocidas para
            este agente, o Q_INITIAL_VALUE si no hay datos.
        """
        return learning._get_max_q_for_task(self._q_table, agent_id)

    @staticmethod
    def _compute_q_reward(
        success: bool,
        latency: float,
        cost: float,
    ) -> float:
        """Calcula la recompensa Q a partir del resultado.

        Delegador de
        :func:`harness.orchestrator.mars_scheduler.learning._compute_q_reward`.

        Args:
            success: Si la ejecucion fue exitosa.
            latency: Latencia en segundos.
            cost: Costo en tokens.

        Returns:
            Recompensa en [0, 1].
        """
        return learning._compute_q_reward(success, latency, cost)

    def _compute_effective_priority(self, task: TaskSpec) -> float:
        """Calcula la prioridad efectiva considerando envejecimiento.

        Delegador de
        :func:`harness.orchestrator.mars_scheduler.learning._compute_effective_priority`.

        Args:
            task: Especificacion de la tarea.

        Returns:
            Prioridad efectiva (mayor = mas urgente).
        """
        return learning._compute_effective_priority(task)

    def _estimate_wait(self) -> float:
        """Estima el tiempo de espera en cola.

        Delegador de
        :func:`harness.orchestrator.mars_scheduler.learning._estimate_wait`.

        Returns:
            Tiempo estimado en segundos.
        """
        return learning._estimate_wait(self._task_queue, self._agents)

    def _is_congested(self) -> bool:
        """Determina si el sistema esta en congestion.

        Delegador de
        :func:`harness.orchestrator.mars_scheduler.learning._is_congested`.

        Returns:
            True si la carga total supera el umbral de congestion.
        """
        return learning._is_congested(self._agents)
