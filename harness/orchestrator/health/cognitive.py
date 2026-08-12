"""Health cognitive — clase ``CognitiveState`` (tracking de progreso).

Extraccion mecanica del modulo original
``harness/orchestrator/health.py`` (sin cambios de logica ni firmas):
detectores de fallos cognitivos (repeater/wanderer/looper/timeout)
delegando datos a SessionTelemetry cuando esta disponible.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.orchestrator.telemetry import SessionTelemetry

from .models import (
    MAX_ALTERNATIONS,
    MAX_LEVEL_DURATION_SEC,
    MAX_REPEATED_SUBTASK,
    MAX_STALLED_SEC,
)

logger = logging.getLogger("harness.orchestrator.health")


class CognitiveState:
    """
    Estado cognitivo de una sesion activa.

    Trackea el historial de ejecucion para detectar:
      - Repeater: misma subtask una y otra vez
      - Wanderer: sin progreso en el plan general
      - Looper: alternando entre mismas subtasks

    DRY: Los datos de subtasks, errores y warnings se delegan a
    SessionTelemetry cuando una referencia esta disponible. En modo
    standalone (sin telemetry) se usa almacenamiento local.
    """

    def __init__(
        self,
        session_id: str,
        telemetry: SessionTelemetry | None = None,
    ) -> None:
        self.session_id = session_id
        self._telemetry = telemetry

        # Almacenamiento local (solo usado cuando NO hay telemetry)
        self._history: list[dict] = []
        self._err_count: int = 0
        self._warn_count: int = 0

        # Campos de progreso (exclusivos de CognitiveState)
        self.last_progress_time: float = time.time()
        self.level_start_time: float = time.time()
        self.current_level_idx: int = 0

    # ------------------------------------------------------------------
    # Properties: delegan a telemetry cuando esta disponible
    # ------------------------------------------------------------------

    @property
    def subtask_history(self) -> list[dict]:
        """Historial plano de subtasks (ultimas 20)."""
        if self._telemetry is not None:
            return self._telemetry.get_subtask_history()[-20:]
        return self._history[-20:]

    @subtask_history.setter
    def subtask_history(self, value: list[dict]) -> None:
        """Setter para compatibilidad con asignaciones directas."""
        if self._telemetry is None:
            self._history = value

    @property
    def errors(self) -> int:
        """Total de errores registrados."""
        if self._telemetry is not None:
            return self._telemetry.get_error_count()
        return self._err_count

    @errors.setter
    def errors(self, value: int) -> None:
        """Setter para compatibilidad con asignaciones directas."""
        if self._telemetry is None:
            self._err_count = value

    @property
    def warnings(self) -> int:
        """Total de warnings registrados."""
        if self._telemetry is not None:
            return self._telemetry.get_warning_count()
        return self._warn_count

    @warnings.setter
    def warnings(self, value: int) -> None:
        """Setter para compatibilidad con asignaciones directas."""
        if self._telemetry is None:
            self._warn_count = value

    # ------------------------------------------------------------------
    # Recording: delega a telemetry cuando esta disponible
    # ------------------------------------------------------------------

    def record_subtask(self, subtask_id: str, agent: str, description: str) -> None:
        """Registra la ejecucion de una subtask para analisis.

        Cuando CognitiveState esta vinculado a SessionTelemetry, delega
        el almacenamiento para evitar duplicacion de datos.
        """
        entry = {
            "subtask_id": subtask_id,
            "agent": agent,
            "description": description,
            "timestamp": time.time(),
        }
        if self._telemetry is not None:
            from harness.orchestrator.telemetry import SubtaskRecord  # lazy import
            record = SubtaskRecord(
                subtask_id=subtask_id,
                agent=agent,
                description=description,
                start_time=time.time(),
                status="success",
            )
            self._telemetry.record_subtask(self.current_level_idx, record)
        else:
            self._history.append(entry)
            # Keep last 20 for analysis
            if len(self._history) > 20:
                self._history = self._history[-20:]

    def record_progress(self) -> None:
        """Registra que hubo progreso (avance a nuevo nivel)."""
        self.last_progress_time = time.time()
        self.level_start_time = time.time()

    def record_error(self) -> None:
        """Registra un error (delega a telemetry si esta disponible)."""
        if self._telemetry is not None:
            self._telemetry.record_error()
        else:
            self._err_count += 1

    def record_warning(self) -> None:
        """Registra un warning (delega a telemetry si esta disponible)."""
        if self._telemetry is not None:
            self._telemetry.record_warning()
        else:
            self._warn_count += 1

    # ------------------------------------------------------------------
    # Cognitive detectors (leen de subtask_history, que resuelve
    # desde telemetry o almacenamiento local)
    # ------------------------------------------------------------------

    def check_repeater(self) -> str | None:
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

    def check_wanderer(self) -> str | None:
        """Detecta si no hay progreso desde hace tiempo."""
        stalled = time.time() - self.last_progress_time
        if stalled > MAX_STALLED_SEC:
            return (
                f"WANDERER detectado: sin progreso por "
                f"{stalled:.0f}s (umbral: {MAX_STALLED_SEC}s)"
            )
        return None

    def check_looper(self) -> str | None:
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

    def check_timeout(self) -> str | None:
        """Detecta si un nivel lleva demasiado tiempo."""
        elapsed = time.time() - self.level_start_time
        if elapsed > MAX_LEVEL_DURATION_SEC:
            return (
                f"TIMEOUT en nivel {self.current_level_idx}: "
                f"{elapsed:.0f}s (umbral: {MAX_LEVEL_DURATION_SEC}s)"
            )
        return None

    def get_health(self) -> dict:
        """Evalua todos los checkers cognitivos."""
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
