"""AdaptivePlanner core — clase principal ``AdaptivePlanner``.

Contiene el estado interno, seleccion de estrategia, registro de
feedback, recomendaciones, re-planificacion y estimacion de niveles.
Los metodos PSMAS viven en ``_PSMASMixin`` (psmas.py) y la
persistencia en ``_PersistenceMixin`` (persistence.py).

Extraccion mecanica del modulo original
``harness/orchestrator/adaptive_planner.py`` (sin cambios de logica
ni firmas).
"""

from __future__ import annotations

import hashlib
import logging

from harness.orchestrator.fanout_gate import SINGLE_AGENT_THRESHOLD

from .constants import (
    REPLAN_FAILURE_RATE,
    REPLAN_MIN_SUBTASKS,
)
from .models import PhasePlan, PlanFeedback, PlanStrategy, StrategyStats
from .persistence import _PersistenceMixin
from .psmas import _PSMASMixin

logger = logging.getLogger(__name__)


class AdaptivePlanner(_PSMASMixin, _PersistenceMixin):
    """
    Planificador adaptativo que aprende de ejecuciones anteriores.

    Incorpora PSMAS (Phase-Scheduled Multi-Agent Systems) para activación
    de agentes por fase angular, logrando ~27.3% de reducción de tokens.

    Uso:
        planner = AdaptivePlanner()

        # Decidir estrategia para una tarea
        strategy = planner.choose_strategy("implementar API REST con Docker")

        # Activar phase scheduling para 3+ agentes
        strategy = planner.choose_strategy(
            "investigar arquitectura",
            agents=["builder", "scientist", "guardian"],
        )
        phase_plan = planner.get_phase_plan()

        # Obtener agentes activos en una fase
        activos = planner.get_active_agents(
            ["builder", "scientist", "guardian"],
            phase_degrees=120.0,
        )

        # Comprimir contexto para agente inactivo
        resumen = planner.compress_context_for_idle(
            "guardian", context_largo, target_tokens=200,
        )

        # Registrar feedback después de ejecución
        planner.record_feedback(feedback)

        # Obtener recomendación
        rec = planner.get_recommendation("implementar API")
    """

    def __init__(
        self,
        storage_path: str | None = None,
        min_samples: int = 3,
    ) -> None:
        """
        Args:
            storage_path: Ruta para persistir estadísticas.
            min_samples: Mínimo de muestras antes de usar ML.
        """
        self._storage_path = storage_path or ""
        self._min_samples = min_samples

        # Estadísticas por estrategia
        self._strategy_stats: dict[str, StrategyStats] = {
            s.value: StrategyStats(strategy=s)
            for s in PlanStrategy
        }

        # Historial de feedback reciente
        self._feedback_history: list[PlanFeedback] = []

        # Mapa de task_hash → mejor estrategia conocida
        self._best_strategies: dict[str, tuple[PlanStrategy, float]] = {}

        # Plan de fases PSMAS (phase-scheduled agents)
        self._phase_plan: PhasePlan = PhasePlan()

        # Persistencia
        if self._storage_path:
            self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def choose_strategy(
        self,
        task: str,
        task_type: str | None = None,
        force_agent: str | None = None,
        known_strategy: PlanStrategy | None = None,
        agents: list[str] | None = None,
    ) -> PlanStrategy:
        """
        Elige la mejor estrategia de plan para una tarea.

        Si se proporcionan 3+ agentes, activa phase scheduling PSMAS
        para reducir tokens manteniendo precisión.

        Args:
            task: Mensaje de la tarea.
            task_type: Tipo detectado (opcional).
            force_agent: Si se forzó un agente específico.
            known_strategy: Estrategia conocida (opcional).
            agents: Lista de agentes disponibles para phase scheduling.

        Returns:
            PlanStrategy recomendada.
        """
        # Si ya hay una estrategia conocida forzada, usarla
        if known_strategy:
            return known_strategy

        # Si hay agente forzado, usar single_agent
        if force_agent:
            return PlanStrategy.SINGLE_AGENT

        # Detectar tipo de tarea
        task_type_actual = task_type or self._detect_task_type(task)
        task_hash = self._hash_task(task)

        # Si ya tenemos una mejor estrategia para esta tarea
        if task_hash in self._best_strategies:
            strategy, confidence = self._best_strategies[task_hash]
            if confidence > 0.7:
                logger.info(
                    "AdaptivePlanner: usando estrategia conocida %s "
                    "(confianza=%.2f) para tarea tipo %s",
                    strategy.value, confidence, task_type_actual,
                )
                self._apply_phase_scheduling(strategy, agents, task_type_actual)
                return strategy

        # Elegir basado en estadísticas + tipo de tarea
        strategy = self._select_by_task_type(task, task_type_actual)

        # Phase scheduling para 3+ agentes
        self._apply_phase_scheduling(strategy, agents, task_type_actual)

        logger.info(
            "AdaptivePlanner: estrategia %s para tarea tipo %s",
            strategy.value, task_type_actual,
        )
        return strategy

    def record_feedback(self, feedback: PlanFeedback) -> None:
        """
        Registra feedback de una ejecución y actualiza estadísticas.

        Args:
            feedback: Feedback de la ejecución.
        """
        # Actualizar estadísticas de estrategia
        stats = self._strategy_stats[feedback.strategy_used.value]
        stats.update(feedback)

        # Guardar en historial
        self._feedback_history.append(feedback)
        if len(self._feedback_history) > 100:
            self._feedback_history = self._feedback_history[-100:]

        # Actualizar mejor estrategia para este tipo de tarea
        key = f"type:{feedback.task_type}"
        if key not in self._best_strategies or feedback.success_rate > self._best_strategies[key][1]:
            self._best_strategies[key] = (feedback.strategy_used, feedback.success_rate)

        # Persistir
        if self._storage_path:
            self._save()

        logger.info(
            "AdaptivePlanner: feedback registrado para %s | "
            "strategy=%s success_rate=%.2f",
            feedback.session_id, feedback.strategy_used.value, feedback.success_rate,
        )

    def get_recommendation(self, task: str) -> dict:
        """
        Obtiene recomendación completa para una tarea.

        Returns:
            Dict con estrategia, confianza, stats y fase PSMAS.
        """
        task_type = self._detect_task_type(task)
        self._hash_task(task)
        strategy = self.choose_strategy(task, task_type)

        stats = self._strategy_stats[strategy.value]
        known = self._best_strategies.get(f"type:{task_type}")

        recommendation: dict = {
            "task_type": task_type,
            "recommended_strategy": strategy.value,
            "confidence": known[1] if known else stats.avg_success_rate,
            "strategy_stats": stats.to_dict(),
            "total_feedback_samples": len(self._feedback_history),
            "alternative_strategies": {
                k: v.to_dict()
                for k, v in self._strategy_stats.items()
                if k != strategy.value and v.total_uses > 0
            },
        }

        # Incluir plan de fases PSMAS si está activo
        phase_plan = self.get_phase_plan()
        if phase_plan.get("agent_phases"):
            recommendation["phase_plan"] = phase_plan

        return recommendation

    def should_replan(
        self,
        feedback: PlanFeedback,
        healing_context: dict | None = None,
    ) -> tuple[bool, str | None]:
        """
        Determina si se debe re-planificar basado en feedback.

        Args:
            feedback: Feedback de la ejecución actual.
            healing_context: Contexto de self-healing (opcional).

        Returns:
            (debe_replanificar, razón)
        """
        # Si la tasa de éxito es muy baja
        if feedback.success_rate < REPLAN_FAILURE_RATE and feedback.subtask_count > REPLAN_MIN_SUBTASKS:
            return True, f"failure_rate={feedback.success_rate:.2f} (umbral={REPLAN_FAILURE_RATE})"

        # Si hay contexto de self-healing y muestra problemas
        if healing_context:
            stalled_warnings = healing_context.get("stalled_warnings", 0)
            if stalled_warnings >= 2:
                return True, f"{stalled_warnings} stall warnings consecutivos"

        # Si hay alternancias (looper) en el historial
        recent = self._feedback_history[-5:] if len(self._feedback_history) >= 5 else self._feedback_history
        consecutivo_failures = sum(1 for f in recent if f.success_rate < REPLAN_FAILURE_RATE)
        if len(recent) >= 3 and consecutivo_failures >= 2:
            return True, f"{consecutivo_failures}/{len(recent)} ejecuciones recientes fallaron"

        return False, None

    def estimate_levels(self, task: str, strategy: PlanStrategy) -> int:
        """
        Estima el número óptimo de niveles para una tarea.

        Args:
            task: Mensaje de la tarea.
            strategy: Estrategia elegida.

        Returns:
            Número de niveles recomendados.
        """
        if strategy == PlanStrategy.SINGLE_AGENT:
            return 1
        elif strategy == PlanStrategy.SEQUENTIAL:
            # Estimar basado en complejidad del texto
            word_count = len(task.split())
            if word_count < 10:
                return 1
            elif word_count < 30:
                return 2
            elif word_count < 60:
                return 3
            else:
                return 4
        elif strategy == PlanStrategy.FAN_OUT_FAN_IN:
            return 2  # fan-out → fan-in
        else:  # HYBRID
            return 3

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _detect_task_type(self, task: str) -> str:
        """Detecta el tipo de tarea del mensaje."""
        if not task:
            return "unknown"

        msg_lower = task.lower()

        # Mapping de keywords a tipos
        type_keywords = {
            "deploy": ["deploy", "desplegar", "deployment", "release"],
            "implement": ["implement", "implementar", "create", "crear", "build", "construir"],
            "research": ["research", "investigar", "study", "analizar", "analyze"],
            "test": ["test", "testing", "probar", "validar", "validate"],
            "refactor": ["refactor", "refactorizar", "optimizar", "optimize"],
            "document": ["document", "documentar", "docs", "readme"],
            "design": ["design", "diseñar", "architecture", "arquitectura"],
            "fix": ["fix", "bug", "arreglar", "reparar", "error", "issue"],
        }

        for ttype, keywords in type_keywords.items():
            if any(kw in msg_lower for kw in keywords):
                return ttype

        return "general"

    def _hash_task(self, task: str) -> str:
        """Hash del mensaje para identificar tareas similares."""
        # Normalizar: lowercase, strip, sort words
        words = sorted(task.lower().strip().split())
        normalized = " ".join(words)
        return hashlib.md5(normalized.encode(), usedforsecurity=False).hexdigest()[:12]

    def _degrade_if_strong(self, strategy: PlanStrategy) -> PlanStrategy:
        """Gate anti-sobre-descomposicion (ADR-0075, arXiv:2602.07787).

        Args:
            strategy: Estrategia seleccionada.

        Returns:
            SINGLE_AGENT si el baseline single-agent tiene evidencia
            (>= min_samples) con success rate >= umbral (el multi solo
            anade ruido x17.2); la estrategia original en cualquier otro
            caso (incluido cuando single no tiene datos: no hay baseline).
        """
        single_stats = self._strategy_stats[PlanStrategy.SINGLE_AGENT.value]
        if (
            strategy is not PlanStrategy.SINGLE_AGENT
            and single_stats.total_uses >= self._min_samples
            and single_stats.avg_success_rate >= SINGLE_AGENT_THRESHOLD
        ):
            logger.info(
                "adaptive_planner: baseline single-agent %.2f >= %.2f (%d usos); "
                "degradando %s a SINGLE_AGENT (anti-sobre-descomposicion)",
                single_stats.avg_success_rate, SINGLE_AGENT_THRESHOLD,
                single_stats.total_uses, strategy.value,
            )
            return PlanStrategy.SINGLE_AGENT
        return strategy

    def _select_by_task_type(self, task: str, task_type: str) -> PlanStrategy:
        """Selecciona estrategia basada en tipo de tarea."""
        # Verificar si tenemos datos para este tipo
        key = f"type:{task_type}"
        if key in self._best_strategies:
            learned = self._best_strategies[key]
            return self._degrade_if_strong(learned[0])

        # Reglas heurísticas por tipo
        type_strategy = {
            "deploy": PlanStrategy.SEQUENTIAL,
            "implement": PlanStrategy.HYBRID,
            "research": PlanStrategy.SINGLE_AGENT,
            "test": PlanStrategy.SEQUENTIAL,
            "refactor": PlanStrategy.SEQUENTIAL,
            "document": PlanStrategy.SINGLE_AGENT,
            "design": PlanStrategy.HYBRID,
            "fix": PlanStrategy.SINGLE_AGENT,
            "general": PlanStrategy.HYBRID,
        }

        base_strategy = type_strategy.get(task_type, PlanStrategy.HYBRID)

        # Si la estrategia tiene pocas muestras, usar default
        stats = self._strategy_stats[base_strategy.value]
        if stats.total_uses < self._min_samples:
            return base_strategy

        # Elegir la estrategia con mejor performance histórico
        best_strategy = base_strategy
        best_rate = stats.avg_success_rate

        for s_stats in self._strategy_stats.values():
            if s_stats.total_uses >= self._min_samples and s_stats.avg_success_rate > best_rate:
                best_rate = s_stats.avg_success_rate
                best_strategy = s_stats.strategy

        return self._degrade_if_strong(best_strategy)
