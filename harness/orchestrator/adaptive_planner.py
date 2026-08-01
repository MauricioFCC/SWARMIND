"""
Adaptive Planning — meta-agente que ajusta la topología del plan
basado en feedback de ejecuciones anteriores.

Características:
  - Ajusta niveles según historial de éxito/fracaso
  - Re-planifica si un nivel falla consistentemente
  - Aprende qué estructuras de plan funcionan mejor por tipo de tarea
  - Integra con FederatedMemory y AgentKpiTracker
  - Phase-Scheduled Multi-Agent Systems (PSMAS, arXiv 2604.17400, abril 2026)
    para activación de agentes por fase y reducción de tokens

Basado en investigación Princeton NLP 2026 + Microsoft AutoGen:
  - Single-agent supera multi-agent en 64% de tareas benchmark
  - Multi-agent añade ~2.1 puntos de precisión al doble de costo
  - Adaptive Planning decide dinámicamente la estructura óptima
  - PSMAS logra 27.3% de reducción de tokens con agentes phase-scheduled
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

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

# PSMAS: Fases angulares por agente (grados)
PHASE_BUILDER = 0.0      # Siempre activo
PHASE_SCIENTIST = 120.0  # Fase de investigación/análisis
PHASE_GUARDIAN = 240.0   # Fase de revisión/calidad

# Ventana angular por defecto para activación (grados)
PSMAS_DEFAULT_WINDOW = 60.0

# Umbral de agentes para activar phase scheduling
PSMAS_MIN_AGENTS = 3

# Agentes siempre activos (fase 0)
ALWAYS_ACTIVE_AGENTS = {"builder", "planner", "coordinator", "orchestrator"}


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
    metadata: dict = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
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

    def to_dict(self) -> dict:
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


@dataclass
class PhasePlan:
    """
    Plan de fases PSMAS para un conjunto de agentes.

    Almacena la asignación de fase angular por agente y el tipo de tarea
    para el cual fue generado el plan.
    """
    agent_phases: dict[str, float] = field(default_factory=dict)
    task_type: str = ""
    window_degrees: float = PSMAS_DEFAULT_WINDOW
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "agent_phases": dict(self.agent_phases),
            "task_type": self.task_type,
            "window_degrees": self.window_degrees,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# AdaptivePlanner
# ---------------------------------------------------------------------------

class AdaptivePlanner:
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

    def _apply_phase_scheduling(
        self,
        strategy: PlanStrategy,
        agents: list[str] | None,
        task_type: str,
    ) -> None:
        """
        Aplica phase scheduling PSMAS si hay suficientes agentes.

        Solo se activa cuando:
          - Hay 3+ agentes en la lista
          - La estrategia lo soporta (HYBRID o FAN_OUT_FAN_IN)

        Args:
            strategy: Estrategia seleccionada.
            agents: Lista de agentes disponibles.
            task_type: Tipo de tarea detectado.
        """
        if not agents or len(agents) < PSMAS_MIN_AGENTS:
            self._phase_plan = PhasePlan()
            return

        # Phase scheduling es más efectivo con estrategias multi-agente
        if strategy in (PlanStrategy.HYBRID, PlanStrategy.FAN_OUT_FAN_IN):
            self._phase_plan = PhasePlan(
                agent_phases=self._assign_agent_phases(agents, task_type),
                task_type=task_type,
            )
            logger.info(
                "PSMAS: phase plan asignado para %d agentes "
                "(estrategia=%s, tipo=%s)",
                len(agents), strategy.value, task_type,
            )
        else:
            # Con estrategias single/secuencial, fase 0 para todos
            self._phase_plan = PhasePlan(
                agent_phases={a: 0.0 for a in agents},
                task_type=task_type,
            )

    def _assign_agent_phases(
        self,
        agents: list[str],
        task_type: str,
    ) -> dict[str, float]:
        """
        Asigna fase angular (0-360°) a cada agente según PSMAS.

        La técnica PSMAS (arXiv 2604.17400, abril 2026) asigna fases
        angulares a los agentes para activarlos solo en su ventana
        programada, logrando 27.3% de reducción de tokens.

        Reglas de asignación:
          - builder/planner/coordinator → fase 0° (siempre activos)
          - scientist/researcher → fase 120°
          - guardian/quality/reviewer → fase 240°
          - Otros agentes sin dependencias → misma fase (paralelo)

        Args:
            agents: Lista de IDs de agentes.
            task_type: Tipo de tarea (influye en asignación).

        Returns:
            Dict[str, float] mapeando agente → fase en grados.
        """
        phases: dict[str, float] = {}
        n = len(agents)
        if n == 0:
            return phases

        # Contadores para distribución uniforme de agentes genéricos
        generic_idx = 0

        for agent in agents:
            agent_lower = agent.lower()

            # Agentes siempre activos en fase 0
            if agent_lower in ALWAYS_ACTIVE_AGENTS:
                phases[agent] = PHASE_BUILDER

            # Científicos / investigadores en fase 120°
            elif any(kw in agent_lower for kw in ("scientist", "research", "analyst")):
                phases[agent] = PHASE_SCIENTIST

            # Guardianes / revisores en fase 240°
            elif any(kw in agent_lower for kw in ("guardian", "quality", "review", "audit")):
                phases[agent] = PHASE_GUARDIAN

            else:
                # Agentes genéricos: distribuir uniformemente
                # Los que comparten fase pueden ejecutarse en paralelo
                if generic_idx % 3 == 0:
                    phases[agent] = PHASE_BUILDER
                elif generic_idx % 3 == 1:
                    phases[agent] = PHASE_SCIENTIST
                else:
                    phases[agent] = PHASE_GUARDIAN
                generic_idx += 1

        return phases

    def get_active_agents(
        self,
        agents: list[str],
        phase_degrees: float,
        window: float = PSMAS_DEFAULT_WINDOW,
    ) -> list[str]:
        """
        Retorna solo agentes dentro de la ventana angular desde ``phase_degrees``.

        Los agentes fuera de la ventana reciben context summaries
        comprimidos para ahorrar tokens.

        Args:
            agents: Lista de agentes a filtrar.
            phase_degrees: Fase actual del ciclo (0-360°).
            window: Ventana angular en grados (default 60°).

        Returns:
            Lista de agentes activos en la fase actual.
        """
        if not agents:
            return []

        # Sin plan de fases: todos activos
        if not self._phase_plan.agent_phases:
            return agents

        active: list[str] = []
        seen: set = set()

        # Primera pasada: agentes dentro de la ventana
        for agent in agents:
            agent_phase = self._phase_plan.agent_phases.get(agent, 0.0)
            # Distancia angular mínima (circular)
            diff = abs(agent_phase - phase_degrees) % 360.0
            diff = min(diff, 360.0 - diff)

            if diff <= window:
                active.append(agent)
                seen.add(agent)

        # Segunda pasada: siempre incluir agentes en fase 0 (críticos)
        for agent in agents:
            if agent in seen:
                continue
            agent_phase = self._phase_plan.agent_phases.get(agent, 0.0)
            if agent_phase == PHASE_BUILDER:
                active.append(agent)
                seen.add(agent)

        # Tercera pasada: si no hay activos, incluir los más cercanos
        if not active:
            # Encontrar agente más cercano a la fase actual
            closest = min(
                agents,
                key=lambda a: min(
                    abs(self._phase_plan.agent_phases.get(a, 0.0) - phase_degrees) % 360.0,
                    360.0 - abs(self._phase_plan.agent_phases.get(a, 0.0) - phase_degrees) % 360.0,
                ),
            )
            active.append(closest)

        logger.debug(
            "PSMAS get_active_agents: phase=%s, window=%s, "
            "activos=%d/%d",
            phase_degrees, window, len(active), len(agents),
        )

        return active

    def compress_context_for_idle(
        self,
        agent_id: str,
        context: str,
        target_tokens: int,
    ) -> str:
        """
        Comprime el contexto para agentes inactivos (solo envían summary).

        Extrae líneas con información esencial y descarta el resto,
        reduciendo drásticamente el consumo de tokens.

        Args:
            agent_id: ID del agente destino (para logging).
            context: Contexto original completo.
            target_tokens: Tokens objetivo para el resumen comprimido.

        Returns:
            Contexto comprimido (solo información esencial).
        """
        if not context:
            return ""

        # Estimación rápida de tokens (chars/4)
        estimated_tokens = max(1, len(context) // 4)
        if estimated_tokens <= target_tokens:
            return context

        # Líneas con información esencial
        essential_keywords = [
            "task:", "goal:", "objective:", "output:", "result:",
            "decision:", "conclusion:", "summary:", "resumen:",
            "requerim", "requisito", "api:", "endpoint:",
            "error:", "warning:", "critical:", "importante:",
            "strategy:", "plan:", "status:", "progress:",
        ]

        lines = context.split("\n")
        essential_lines: list[str] = []
        header_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Mantener encabezados de sección
            if stripped.startswith(("###", "===")):
                header_lines.append(stripped)
                continue

            # Mantener líneas con palabras clave
            if any(kw in stripped.lower() for kw in essential_keywords):
                essential_lines.append(stripped)

        # Combinar encabezados + líneas esenciales
        compressed = "\n".join(header_lines + essential_lines)

        # Si aún excede, truncar por tokens
        if len(compressed) // 4 > target_tokens:
            char_limit = target_tokens * 4
            compressed = compressed[:char_limit] + (
                "\n[...truncated for idle agent...]"
            )

        # Si no hay nada esencial, tomar las primeras líneas significativas
        if not compressed.strip():
            meaningful = [line for line in lines if line.strip()][
                :max(3, target_tokens // 10)
            ]
            compressed = "\n".join(meaningful)

        logger.debug(
            "PSMAS compress_context: agente=%s, %d → %d tokens (objetivo=%d)",
            agent_id, estimated_tokens, max(1, len(compressed) // 4),
            target_tokens,
        )

        return compressed

    def get_phase_plan(self) -> dict:
        """
        Obtiene el plan de fases PSMAS actual.

        Returns:
            Dict con agent_phases, task_type, window, created_at.
            Vacío si no hay phase scheduling activo.
        """
        return self._phase_plan.to_dict()

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
        import hashlib
        # Normalizar: lowercase, strip, sort words
        words = sorted(task.lower().strip().split())
        normalized = " ".join(words)
        return hashlib.md5(normalized.encode(), usedforsecurity=False).hexdigest()[:12]

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

        for s_stats in self._strategy_stats.values():
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

        Path(self._storage_path).parent.mkdir(parents=True, exist_ok=True)

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

        if not Path(self._storage_path).exists():
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
