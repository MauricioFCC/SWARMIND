"""
Agent Health Check — 3 niveles de verificación para sistemas multi-agente.

Basado en investigación 2026 de Zylos Research y StatusCake:
  - Liveness:   ¿El proceso/sistema está vivo?
  - Readiness:  ¿Puede aceptar y procesar tareas?
  - Cognitive:  ¿Está progresando o atascado en loops?

Integra con TaskOrchestrator para detectar:
  - Repeater: misma subtask repetida sin cambio de estado
  - Wanderer: agente activo pero sin progreso en el plan
  - Looper: alternancia entre 2+ subtasks sin avance real
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Umbrales para detección de fallos cognitivos
MAX_REPEATED_SUBTASK = 3       # Misma subtask ejecutada N veces = repeater
MAX_LEVEL_DURATION_SEC = 300   # 5 minutos por nivel = timeout
MAX_STALLED_SEC = 120          # 2 minutos sin progreso = wanderer
MAX_ALTERNATIONS = 5           # Alternancias entre mismas subtasks = looper


# ---------------------------------------------------------------------------
# Health status
# ---------------------------------------------------------------------------

@dataclass
class HealthStatus:
    """Resultado de un health check."""
    healthy: bool
    level: str                # liveness | readiness | cognitive
    status: str               # ok | warning | critical
    message: str
    details: Dict = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict:
        return {
            "healthy": self.healthy,
            "level": self.level,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Cognitive state: tracking para detectar fallos de progreso
# ---------------------------------------------------------------------------

@dataclass
class CognitiveState:
    """
    Estado cognitivo de una sesión activa.

    Trackea el historial de ejecución para detectar:
      - Repeater: misma subtask una y otra vez
      - Wanderer: sin progreso en el plan general
      - Looper: alternando entre mismas subtasks
    """
    session_id: str
    subtask_history: List[Dict] = field(default_factory=list)
    last_progress_time: float = field(default_factory=time.time)
    level_start_time: float = field(default_factory=time.time)
    current_level_idx: int = 0
    errors: int = 0
    warnings: int = 0

    def record_subtask(self, subtask_id: str, agent: str, description: str) -> None:
        """Registra la ejecución de una subtask para análisis."""
        self.subtask_history.append({
            "subtask_id": subtask_id,
            "agent": agent,
            "description": description,
            "timestamp": time.time(),
        })
        # Keep last 20 for analysis
        if len(self.subtask_history) > 20:
            self.subtask_history = self.subtask_history[-20:]

    def record_progress(self) -> None:
        """Registra que hubo progreso (avance a nuevo nivel)."""
        self.last_progress_time = time.time()
        self.level_start_time = time.time()

    def record_error(self) -> None:
        """Registra un error."""
        self.errors += 1

    def check_repeater(self) -> Optional[str]:
        """Detecta si la misma subtask se repite sin cambio."""
        if len(self.subtask_history) < MAX_REPEATED_SUBTASK:
            return None
        recent = self.subtask_history[-MAX_REPEATED_SUBTASK:]
        ids = [s["subtask_id"] for s in recent]
        if len(set(ids)) == 1:
            return (
                f"REPEATER detectado: subtask '{ids[0]}' "
                f"ejecutada {MAX_REPEATED_SUBTASK} veces seguidas"
            )
        return None

    def check_wanderer(self) -> Optional[str]:
        """Detecta si no hay progreso desde hace tiempo."""
        stalled = time.time() - self.last_progress_time
        if stalled > MAX_STALLED_SEC:
            return (
                f"WANDERER detectado: sin progreso por "
                f"{stalled:.0f}s (umbral: {MAX_STALLED_SEC}s)"
            )
        return None

    def check_looper(self) -> Optional[str]:
        """Detecta alternancia entre mismas subtasks."""
        if len(self.subtask_history) < MAX_ALTERNATIONS:
            return None
        recent = self.subtask_history[-MAX_ALTERNATIONS:]
        ids = [s["subtask_id"] for s in recent]
        # Check if it's alternating between 2-3 subtasks
        unique = list(dict.fromkeys(ids))  # preserve order
        if len(unique) <= 3 and len(unique) < len(ids):
            return (
                f"LOOPER detectado: alternando entre "
                f"{len(unique)} subtasks: {', '.join(unique)}"
            )
        return None

    def check_timeout(self) -> Optional[str]:
        """Detecta si un nivel lleva demasiado tiempo."""
        elapsed = time.time() - self.level_start_time
        if elapsed > MAX_LEVEL_DURATION_SEC:
            return (
                f"TIMEOUT en nivel {self.current_level_idx}: "
                f"{elapsed:.0f}s (umbral: {MAX_LEVEL_DURATION_SEC}s)"
            )
        return None

    def get_health(self) -> Dict:
        """Evalúa todos los checkers cognitivos."""
        issues = []
        for check in [self.check_repeater, self.check_wanderer,
                       self.check_looper, self.check_timeout]:
            result = check()
            if result:
                issues.append(result)

        return {
            "healthy": len(issues) == 0,
            "issues": issues,
            "subtasks_executed": len(self.subtask_history),
            "errors": self.errors,
            "warnings": self.warnings,
            "last_progress_ago": f"{(time.time() - self.last_progress_time):.0f}s",
        }


# ---------------------------------------------------------------------------
# AgentHealthChecker
# ---------------------------------------------------------------------------

class AgentHealthChecker:
    """
    Health Checker multi-nivel para sistemas de agentes.

    Uso:
        checker = AgentHealthChecker(vector_store=store)
        status = checker.check_all()
        if not status["cognitive"].healthy:
            # tomar acción correctiva
    """

    def __init__(self, vector_store: Optional[Any] = None) -> None:
        self._store = vector_store
        self._cognitive_states: Dict[str, CognitiveState] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_liveness(self) -> HealthStatus:
        """
        Nivel 1: Liveness Check.

        Verifica que el sistema base responda:
          - Importaciones básicas funcionan
          - Directorios esenciales existen
          - Módulos core cargan correctamente
        """
        issues = []

        # Check 1: imports básicos
        try:
            from harness.orchestrator.agent_bus import AgentBus  # noqa
            from harness.orchestrator.task_planner import TaskPlanner  # noqa
        except ImportError as e:
            issues.append(f"ImportError: {e}")

        # Check 2: directorios esenciales (desde harness/)
        from pathlib import Path
        base = Path(__file__).parent.parent  # harness/
        essential = [
            base / "orchestrator",
            base / "tests",
        ]
        for d in essential:
            if not d.exists():
                issues.append(f"Directorio faltante: {d}")

        healthy = len(issues) == 0
        return HealthStatus(
            healthy=healthy,
            level="liveness",
            status="ok" if healthy else "critical",
            message="Sistema vivo" if healthy else f"Issues: {'; '.join(issues)}",
            details={"issues": issues, "base_path": str(base)},
        )

    def check_readiness(self) -> HealthStatus:
        """
        Nivel 2: Readiness Check.

        Verifica que el sistema pueda procesar tareas:
          - LanceDB conectado (si aplica)
          - Agentes disponibles
          - Skills registrados
          - TaskPlanner funciona
        """
        issues = []

        # Check 1: TaskPlanner básico
        try:
            from harness.orchestrator.task_planner import TaskPlanner
            planner = TaskPlanner()
            plan = planner.decompose("test health check")
            subtask_count = len(plan.subtasks)
        except Exception as e:
            issues.append(f"TaskPlanner error: {e}")
            subtask_count = 0

        # Check 2: Agentes disponibles
        try:
            from harness.orchestrator.agent_discovery import discover_agents_recursive
            agents = discover_agents_recursive()
            agent_count = len(agents)
        except Exception as e:
            issues.append(f"Agent discovery error: {e}")
            agent_count = 0

        # Check 3: LanceDB (si está configurado)
        db_ok = False
        if self._store is not None:
            try:
                dummy_vec = np.zeros(384, dtype=np.float32)
                self._store.search("health_check", dummy_vec, top_k=1)
                db_ok = True
            except Exception as e:
                issues.append(f"LanceDB error: {e}")

        healthy = len(issues) == 0 and agent_count >= 5 and subtask_count > 0
        return HealthStatus(
            healthy=healthy,
            level="readiness",
            status="ok" if healthy else "degraded" if agent_count > 0 else "critical",
            message=(
                f"{agent_count} agents, {subtask_count} subtask templates"
                if healthy else f"Issues: {'; '.join(issues)}"
            ),
            details={
                "agents_available": agent_count,
                "subtask_templates": subtask_count,
                "database_ok": db_ok,
                "issues": issues,
            },
        )

    def check_cognitive(self, session_id: Optional[str] = None) -> HealthStatus:
        """
        Nivel 3: Cognitive Check.

        Verifica que las sesiones activas estén progresando:
          - No hay Repeater (misma subtask repetida)
          - No hay Wanderer (sin progreso)
          - No hay Looper (alternancia sin avance)
          - No hay Timeout (nivel muy largo)

        Args:
            session_id: Si se especifica, solo checkea esa sesión.
                        Si es None, checkea todas las sesiones trackeadas.
        """
        issues = []
        sessions_to_check = []

        if session_id:
            state = self._cognitive_states.get(session_id)
            if state:
                sessions_to_check = [state]
            else:
                issues.append(f"Sesión '{session_id}' no encontrada")
        else:
            sessions_to_check = list(self._cognitive_states.values())

        if not sessions_to_check:
            # No hay sesiones activas — es normal si está ocioso
            return HealthStatus(
                healthy=True,
                level="cognitive",
                status="ok",
                message="Sin sesiones activas (sistema ocioso)",
                details={"active_sessions": 0},
            )

        all_healthy = True
        session_details = {}
        for state in sessions_to_check:
            health = state.get_health()
            session_details[state.session_id] = health
            if not health["healthy"]:
                all_healthy = False
                issues.extend(health["issues"])

        healthy = all_healthy and len(issues) == 0
        return HealthStatus(
            healthy=healthy,
            level="cognitive",
            status="ok" if healthy else "warning",
            message=(
                f"{len(sessions_to_check)} sesiones OK"
                if healthy else f"Issues: {'; '.join(issues[:3])}"
            ),
            details={
                "active_sessions": len(sessions_to_check),
                "sessions": session_details,
                "issues": issues,
            },
        )

    def check_all(self) -> Dict[str, HealthStatus]:
        """
        Ejecuta los 3 niveles de health check.

        Returns:
            Dict con 'liveness', 'readiness', 'cognitive'.
        """
        return {
            "liveness": self.check_liveness(),
            "readiness": self.check_readiness(),
            "cognitive": self.check_cognitive(),
        }

    def check_all_dict(self) -> Dict:
        """check_all() como dicts serializables."""
        result = self.check_all()
        return {
            k: v.to_dict() for k, v in result.items()
        }

    # ------------------------------------------------------------------
    # Cognitive state management
    # ------------------------------------------------------------------

    def get_or_create_cognitive_state(self, session_id: str) -> CognitiveState:
        """Obtiene o crea el estado cognitivo para una sesión."""
        if session_id not in self._cognitive_states:
            self._cognitive_states[session_id] = CognitiveState(session_id=session_id)
        return self._cognitive_states[session_id]

    def record_subtask(
        self, session_id: str, subtask_id: str,
        agent: str, description: str,
    ) -> None:
        """Registra una subtask ejecutada y verifica salud cognitiva."""
        state = self.get_or_create_cognitive_state(session_id)
        state.record_subtask(subtask_id, agent, description)

    def record_progress(self, session_id: str) -> None:
        """Registra progreso (avance de nivel) en una sesión."""
        state = self._cognitive_states.get(session_id)
        if state:
            state.record_progress()

    def record_error(self, session_id: str) -> None:
        """Registra un error en una sesión."""
        state = self._cognitive_states.get(session_id)
        if state:
            state.record_error()

    def get_cognitive_issues(self, session_id: str) -> List[str]:
        """Obtiene issues cognitivos de una sesión."""
        state = self._cognitive_states.get(session_id)
        if not state:
            return []
        return [i for i in [
            state.check_repeater(),
            state.check_wanderer(),
            state.check_looper(),
            state.check_timeout(),
        ] if i is not None]

    def cleanup_stale_sessions(self, max_age_sec: int = 3600) -> int:
        """Limpia sesiones cognitivas viejas (inactivas > max_age_sec)."""
        now = time.time()
        stale = [
            sid for sid, state in self._cognitive_states.items()
            if now - state.last_progress_time > max_age_sec
        ]
        for sid in stale:
            del self._cognitive_states[sid]
        if stale:
            logger.info("Cleaned %d stale cognitive sessions.", len(stale))
        return len(stale)
