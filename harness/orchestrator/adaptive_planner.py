"""
Adaptive Planning — meta-agente que ajusta la topología del plan
basado en feedback de ejecuciones anteriores.

Características:
  - Ajusta niveles según historial de éxito/fracaso
  - Re-planifica si un nivel falla consistentemente
  - Aprende qué estructuras de plan funcionan mejor por tipo de tarea
  - Integra con FederatedMemory y AgentKpiTracker

Basado en investigación Princeton NLP 2026 + Microsoft AutoGen:
  - Single-agent supera multi-agent en 64% de tareas benchmark
  - Multi-agent añade ~2.1 puntos de precisión al doble de costo
  - Adaptive Planning decide dinámicamente la estructura óptima
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Umbrales para decisión de re-planificar
REPLAN_FAILURE_RATE = 0.5       # Si >50% de subtasks fallan → re-plan
REPLAN_STALLED_LEVELS = 2       # Si 2+ niveles seguidos sin progreso → re-plan
REPLAN_MIN_SUBTASKS = 1         # Mínimo subtasks en un plan

# Modos de plan
MODE_SINGLE_AGENT = "single_agent"
MODE_SEQUENTIAL = "sequential"
MODE_PARALLEL = "parallel"
MODE_HYBRID = "hybrid"          # Mezcla de sequential + parallel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PlanStrategy(str, Enum):
    """Estrategia de planificación disponible."""
    SINGLE_AGENT = "single_agent"     # 1 agente hace todo
    SEQUENTIAL = "sequential"          # Pasos lineales
    FAN_OUT_FAN_IN = "fan_out_fan_in" # Paralelo → consolidar
    HYBRID = "hybrid"                 # Mezcla adaptativa


class AdaptationTrigger(str, Enum):
    """Razón por la que se gatilló una adaptación."""
    HIGH_FAILURE_RATE = "high_failure_rate"
    STALLED_PROGRESS = "stalled_progress"
    LEVEL_TIMEOUT = "level_timeout"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    REPEATER_DETECTED = "repeater_detected"
    LOOPER_DETECTED = "looper_detected"
    MANUAL_OVERRIDE = "manual_override"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PlanFeedback:
    """Feedback de una ejecución de plan."""
    session_id: str
    task_hash: str                # Hash del mensaje original
    task_type: str                # deploy | implement | research | etc
    strategy_used: PlanStrategy
    subtask_count: int
    level_count: int
    success_count: int
    failure_count: int
    total_duration_ms: float
    success_rate: float
    adaptation_triggered: bool = False
    adaptation_reason: str = ""
    metadata: Dict = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "task_hash": self.task_hash,
            "task_type": self.task_type,
            "strategy_used": self.strategy_used.value,
            "subtask_count": self.subtask_count,
            "level_count": self.level_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "success_rate": round(self.success_rate, 4),
            "adaptation_triggered": self.adaptation_triggered,
            "adaptation_reason": self.adaptation_reason,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass
class StrategyStats:
    """Estadísticas de una estrategia de plan."""
    strategy: PlanStrategy
    total_uses: int = 0
    total_successes: int = 0
    total_failures: int = 0
    avg_duration_ms: float = 0.0
    avg_success_rate: float = 0.0
    last_used: str = ""

    @property
    def success_rate(self) -> float:
        return (
            self.total_successes / self.total_uses
            if self.total_uses > 0 else 0.0
        )

    def update(self, feedback: PlanFeedback) -> None:
        """Actualiza estadísticas con un feedback."""
        self.total_uses += 1
        if feedback.success_rate >= 0.7:
            self.total_successes += 1
        else:
            self.total_failures += 1

        # Running average
        self.avg_duration_ms = (
            (self.avg_duration_ms * (self.total_uses - 1) + feedback.total_duration_ms)
            / self.total_uses
        )
        self.avg_success_rate = (
            (self.avg_success_rate * (self.total_uses - 1) + feedback.success_rate)
            / self.total_uses
        )
        self.last_used = feedback.timestamp

    def to_dict(self) -> Dict:
        return {
            "strategy": self.strategy.value,
            "total_uses": self.total_uses,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "avg_success_rate": round(self.avg_success_rate, 4),
            "success_rate": round(self.success_rate, 4),
            "last_used": self.last_used,
        }


# ---------------------------------------------------------------------------
# AdaptivePlanner
# ---------------------------------------------------------------------------

class AdaptivePlanner:
    """
    Planificador adaptativo que aprende de ejecuciones anteriores.

    Uso:
        planner = AdaptivePlanner()
        
        # Decidir estrategia para una tarea
        strategy = planner.choose_strategy("implementar API REST con Docker")
        
        # Registrar feedback después de ejecución
        planner.record_feedback(feedback)
        
        # Obtener recomendación
        rec = planner.get_recommendation("implementar API")
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
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
        self._strategy_stats: Dict[str, StrategyStats] = {
            s.value: StrategyStats(strategy=s)
            for s in PlanStrategy
        }

        # Historial de feedback reciente
        self._feedback_history: List[PlanFeedback] = []

        # Mapa de task_hash → mejor estrategia conocida
        self._best_strategies: Dict[str, Tuple[PlanStrategy, float]] = {}

        # Persistencia
        if self._storage_path:
            self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def choose_strategy(
        self,
        task: str,
        task_type: Optional[str] = None,
        force_agent: Optional[str] = None,
        known_strategy: Optional[PlanStrategy] = None,
    ) -> PlanStrategy:
        """
        Elige la mejor estrategia de plan para una tarea.

        Args:
            task: Mensaje de la tarea.
            task_type: Tipo detectado (opcional).
            force_agent: Si se forzó un agente específico.
            known_strategy: Estrategia conocida (opcional).

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
        task_type = task_type or self._detect_task_type(task)
        task_hash = self._hash_task(task)

        # Si ya tenemos una mejor estrategia para esta tarea
        if task_hash in self._best_strategies:
            strategy, confidence = self._best_strategies[task_hash]
            if confidence > 0.7:
                logger.info(
                    "AdaptivePlanner: usando estrategia conocida %s "
                    "(confianza=%.2f) para tarea tipo %s",
                    strategy.value, confidence, task_type,
                )
                return strategy

        # Elegir basado en estadísticas + tipo de tarea
        strategy = self._select_by_task_type(task, task_type)
        logger.info(
            "AdaptivePlanner: estrategia %s para tarea tipo %s",
            strategy.value, task_type,
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

    def get_recommendation(self, task: str) -> Dict:
        """
        Obtiene recomendación completa para una tarea.

        Returns:
            Dict con estrategia, confianza, y stats.
        """
        task_type = self._detect_task_type(task)
        task_hash = self._hash_task(task)
        strategy = self.choose_strategy(task, task_type)

        stats = self._strategy_stats[strategy.value]
        known = self._best_strategies.get(f"type:{task_type}")

        return {
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

    def should_replan(
        self,
        feedback: PlanFeedback,
        healing_context: Optional[Dict] = None,
    ) -> Tuple[bool, Optional[str]]:
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
        import hashlib
        # Normalizar: lowercase, strip, sort words
        words = sorted(task.lower().strip().split())
        normalized = " ".join(words)
        return hashlib.md5(normalized.encode()).hexdigest()[:12]

    def _select_by_task_type(self, task: str, task_type: str) -> PlanStrategy:
        """Selecciona estrategia basada en tipo de tarea."""
        # Verificar si tenemos datos para este tipo
        key = f"type:{task_type}"
        if key in self._best_strategies:
            return self._best_strategies[key][0]

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

        for s_name, s_stats in self._strategy_stats.items():
            if s_stats.total_uses >= self._min_samples and s_stats.avg_success_rate > best_rate:
                best_rate = s_stats.avg_success_rate
                best_strategy = s_stats.strategy

        return best_strategy

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """Persiste estadísticas a disco."""
        if not self._storage_path:
            return

        import os
        os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)

        data = {
            "strategy_stats": {
                k: v.to_dict() for k, v in self._strategy_stats.items()
            },
            "best_strategies": {
                k: (v[0].value, v[1])
                for k, v in self._best_strategies.items()
            },
            "feedback_count": len(self._feedback_history),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        with open(self._storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load(self) -> None:
        """Carga estadísticas desde disco."""
        if not self._storage_path:
            return

        import os
        if not os.path.exists(self._storage_path):
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for s_name, s_data in data.get("strategy_stats", {}).items():
                if s_name in self._strategy_stats:
                    stats = self._strategy_stats[s_name]
                    stats.total_uses = s_data.get("total_uses", 0)
                    stats.total_successes = s_data.get("total_successes", 0)
                    stats.total_failures = s_data.get("total_failures", 0)
                    stats.avg_duration_ms = s_data.get("avg_duration_ms", 0.0)
                    stats.avg_success_rate = s_data.get("avg_success_rate", 0.0)
                    stats.last_used = s_data.get("last_used", "")

            for key, (s_value, confidence) in data.get("best_strategies", {}).items():
                try:
                    strategy = PlanStrategy(s_value)
                    self._best_strategies[key] = (strategy, confidence)
                except ValueError:
                    pass

        except (json.JSONDecodeError, OSError) as e:
            logger.warning("AdaptivePlanner: error loading stats: %s", e)
