"""Health cognitive mixin — cognitive check y gestion de sesiones.

Extraccion mecanica del modulo original
``harness/orchestrator/health.py`` (sin cambios de logica ni firmas):
check_cognitive, check_all, check_all_dict y la gestion del estado
cognitivo (crear/registrar/limpiar sesiones).
"""
from __future__ import annotations

import logging
import time

from .cognitive import CognitiveState
from .models import HealthStatus

logger = logging.getLogger("harness.orchestrator.health")


class _CognitiveMixin:
    """Mixin con el check cognitivo y la gestion de sesiones."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_cognitive(self, session_id: str | None = None) -> HealthStatus:
        """
        Nivel 3: Cognitive Check.

        Verifica que las sesiones activas esten progresando:
          - No hay Repeater (misma subtask repetida)
          - No hay Wanderer (sin progreso)
          - No hay Looper (alternancia sin avance)
          - No hay Timeout (nivel muy largo)

        Args:
            session_id: Si se especifica, solo checkea esa sesion.
                        Si es None, checkea todas las sesiones trackeadas.
        """
        issues = []
        sessions_to_check = []

        if session_id:
            state = self._cognitive_states.get(session_id)
            if state:
                sessions_to_check = [state]
            else:
                issues.append(f"Session '{session_id}' no encontrada")
        else:
            sessions_to_check = list(self._cognitive_states.values())

        if not sessions_to_check:
            # No hay sesiones activas — es normal si esta ocioso
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

    def check_all(self) -> dict[str, HealthStatus]:
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

    def check_all_dict(self) -> dict:
        """check_all() como dicts serializables."""
        result = self.check_all()
        return {
            k: v.to_dict() for k, v in result.items()
        }

    # ------------------------------------------------------------------
    # Cognitive state management
    # ------------------------------------------------------------------

    def get_or_create_cognitive_state(self, session_id: str) -> CognitiveState:
        """Obtiene o crea el estado cognitivo para una sesion.

        Si hay un TelemetryTracker configurado, vincula el CognitiveState
        con la SessionTelemetry correspondiente para evitar duplicacion.
        """
        if session_id not in self._cognitive_states:
            telemetry = None
            if self._telemetry_tracker is not None:
                telemetry = self._telemetry_tracker.get_session(session_id)
            self._cognitive_states[session_id] = CognitiveState(
                session_id=session_id,
                telemetry=telemetry,
            )
        return self._cognitive_states[session_id]

    def record_subtask(
        self, session_id: str, subtask_id: str,
        agent: str, description: str,
    ) -> None:
        """Registra una subtask ejecutada y verifica salud cognitiva.

        Si hay un TelemetryTracker, tambien actualiza la telemetria.
        """
        state = self.get_or_create_cognitive_state(session_id)
        state.record_subtask(subtask_id, agent, description)

    def record_progress(self, session_id: str) -> None:
        """Registra progreso (avance de nivel) en una sesion."""
        state = self._cognitive_states.get(session_id)
        if state:
            state.record_progress()

    def record_error(self, session_id: str) -> None:
        """Registra un error en una sesion."""
        state = self._cognitive_states.get(session_id)
        if state:
            state.record_error()

    def get_cognitive_issues(self, session_id: str) -> list[str]:
        """Obtiene issues cognitivos de una sesion."""
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
