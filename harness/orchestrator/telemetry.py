"""
Telemetría estructurada para sistemas multi-agente.

Registra métricas de ejecución por sesión:
  - Tiempo por nivel
  - Subtasks completadas
  - Errores y advertencias
  - Tasa de éxito por agente
  - Latencia de cada paso

Exporta a JSON para post-procesamiento y dashboards.

Design: Single Responsibility — telemetry.py = data RECORDING.
CognitiveState en health.py delega aquí para evitar duplicación de datos.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.orchestrator.golden_signals import GoldenSignals

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SubtaskRecord:
    """Registro de una subtask ejecutada."""
    subtask_id: str
    agent: str
    description: str
    status: str = "pending"       # pending | running | success | failed | retry
    error: str | None = None
    warning: str | None = None
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @property
    def elapsed(self) -> float:
        if self.end_time > 0:
            return (self.end_time - self.start_time) * 1000
        if self.start_time > 0:
            return (time.time() - self.start_time) * 1000
        return 0.0


@dataclass
class LevelRecord:
    """Registro de un nivel de ejecución."""
    level: int
    subtasks: list[SubtaskRecord] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    status: str = "pending"       # pending | running | success | failed

    @property
    def duration_ms(self) -> float:
        if self.end_time > 0:
            return (self.end_time - self.start_time) * 1000
        if self.start_time > 0:
            return (time.time() - self.start_time) * 1000
        return 0.0

    @property
    def success_rate(self) -> float:
        if not self.subtasks:
            return 0.0
        success = sum(1 for s in self.subtasks if s.status == "success")
        return success / len(self.subtasks)

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "subtask_count": len(self.subtasks),
            "success_rate": round(self.success_rate, 3),
        }


@dataclass
class SessionTelemetry:
    """Telemetría completa de una sesión.

    Almacena TODOS los datos de ejecución: subtasks, errores, warnings.
    CognitiveState (health.py) delega aquí para evitar duplicación.
    """
    session_id: str
    task: str
    project: str = ""
    levels: list[LevelRecord] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    status: str = "running"       # running | completed | failed | aborted
    total_subtasks: int = 0
    total_errors: int = 0
    total_warnings: int = 0
    agent_stats: dict[str, dict] = field(default_factory=dict)

    @property
    def total_duration_ms(self) -> float:
        if self.end_time > 0:
            return (self.end_time - self.start_time) * 1000
        return (time.time() - self.start_time) * 1000

    @property
    def success_rate(self) -> float:
        if self.total_subtasks == 0:
            return 0.0
        completed = sum(
            1 for level in self.levels
            for st in level.subtasks if st.status == "success"
        )
        return completed / self.total_subtasks if self.total_subtasks > 0 else 0.0

    def add_level(self, level: LevelRecord) -> None:
        self.levels.append(level)

    def record_subtask(self, level_idx: int, record: SubtaskRecord) -> None:
        """Añade un subtask record y actualiza estadísticas."""
        while len(self.levels) <= level_idx:
            self.levels.append(LevelRecord(level=len(self.levels)))
        self.levels[level_idx].subtasks.append(record)
        self.total_subtasks += 1

        if record.error:
            self.total_errors += 1
        if record.warning:
            self.total_warnings += 1

        # Update agent stats
        agent = record.agent
        if agent not in self.agent_stats:
            self.agent_stats[agent] = {"ok": 0, "error": 0, "total": 0}
        self.agent_stats[agent]["total"] += 1
        if record.status == "success":
            self.agent_stats[agent]["ok"] += 1
        elif record.status == "failed":
            self.agent_stats[agent]["error"] += 1

    # ------------------------------------------------------------------
    # Convenience methods for CognitiveState delegation (DRY)
    # ------------------------------------------------------------------

    def get_subtask_history(self) -> list[dict]:
        """Flat list of all subtask entries, compatible with CognitiveState format.

        Returns:
            List of dicts with keys: subtask_id, agent, description, timestamp.
        """
        history: list[dict] = []
        for level in self.levels:
            for st in level.subtasks:
                history.append({
                    "subtask_id": st.subtask_id,
                    "agent": st.agent,
                    "description": st.description,
                    "timestamp": st.start_time or time.time(),
                })
        return history

    def record_error(self) -> None:
        """Incrementa el contador de errores (delegado desde CognitiveState)."""
        self.total_errors += 1

    def record_warning(self) -> None:
        """Incrementa el contador de warnings (delegado desde CognitiveState)."""
        self.total_warnings += 1

    def get_error_count(self) -> int:
        """Retorna el total de errores."""
        return self.total_errors

    def get_warning_count(self) -> int:
        """Retorna el total de warnings."""
        return self.total_warnings

    # ------------------------------------------------------------------
    # Finalization & export
    # ------------------------------------------------------------------

    def finalize(self, status: str = "completed") -> None:
        self.end_time = time.time()
        self.status = status
        for level in self.levels:
            if level.status == "running":
                level.end_time = time.time()
                level.status = status

    def summary(self) -> dict:
        """Resumen ejecutivo de la sesión."""
        return {
            "session_id": self.session_id,
            "task": self.task,
            "project": self.project,
            "status": self.status,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "levels": len(self.levels),
            "total_subtasks": self.total_subtasks,
            "total_errors": self.total_errors,
            "total_warnings": self.total_warnings,
            "success_rate": round(self.success_rate, 3),
            "agent_stats": self.agent_stats,
        }

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "task": self.task,
            "project": self.project,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "status": self.status,
            "total_subtasks": self.total_subtasks,
            "total_errors": self.total_errors,
            "total_warnings": self.total_warnings,
            "success_rate": round(self.success_rate, 3),
            "agent_stats": self.agent_stats,
            "levels": [level.to_dict() for level in self.levels],
        }


# ---------------------------------------------------------------------------
# TelemetryTracker
# ---------------------------------------------------------------------------

class TelemetryTracker:
    """
    Tracker de telemetría.

    Uso:
        tracker = TelemetryTracker(export_dir="harness/data/telemetry")
        telemetry = tracker.start_session("session-1", "deploy API")
        telemetry.record_subtask(0, subtask_record)
        tracker.export("session-1")
    """

    def __init__(self, export_dir: str = "harness/data/telemetry") -> None:
        self._export_dir = Path(export_dir)
        self._export_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, SessionTelemetry] = {}
        self._golden_signals = None  # GoldenSignals (ADR-0034), lazy import

    # ------------------------------------------------------------------
    # Golden Signals (ADR-0034)
    # ------------------------------------------------------------------

    def enable_golden_signals(self, **kwargs) -> GoldenSignals:
        """Habilita Golden Signals LLM en este tracker (Composition Root).

        Args:
            **kwargs: argumentos para GoldenSignals (cost_input_per_1k,
                cost_output_per_1k, cache_read_discount).

        Returns:
            La instancia de GoldenSignals creada.
        """
        from harness.orchestrator.golden_signals import GoldenSignals
        if self._golden_signals is None:
            self._golden_signals = GoldenSignals(**kwargs)
        return self._golden_signals

    @property
    def golden_signals(self):
        """Acceso a GoldenSignals (None si no está habilitado)."""
        return self._golden_signals

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def start_session(
        self, session_id: str, task: str, project: str = "",
    ) -> SessionTelemetry:
        """Inicia una sesión de telemetría."""
        telemetry = SessionTelemetry(
            session_id=session_id,
            task=task,
            project=project,
        )
        self._sessions[session_id] = telemetry
        logger.info(
            "Telemetry: started session %s | task=%s | project=%s",
            session_id, task, project or "default",
        )
        return telemetry

    def get_session(self, session_id: str) -> SessionTelemetry | None:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())

    def finalize_session(self, session_id: str, status: str = "completed") -> None:
        """Finaliza una sesión y la exporta."""
        telemetry = self._sessions.get(session_id)
        if telemetry:
            telemetry.finalize(status)
            self.export(session_id)
            logger.info(
                "Telemetry: finalized session %s | status=%s | duration=%.1fs",
                session_id, status, telemetry.total_duration_ms / 1000,
            )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(self, session_id: str) -> str | None:
        """Exporta la telemetría de una sesión a JSON."""
        telemetry = self._sessions.get(session_id)
        if not telemetry:
            return None

        filename = f"telemetry_{session_id}.json"
        filepath = self._export_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(telemetry.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info("Telemetry: exported to %s", filepath)
        return str(filepath)

    def export_all(self) -> list[str]:
        """Exporta todas las sesiones."""
        return [self.export(sid) for sid in self._sessions if self.export(sid)]

    def export_summary(self) -> str:
        """Exporta un resumen de todas las sesiones."""
        summary = {
            "export_time": datetime.now(timezone.utc).isoformat(),
            "total_sessions": len(self._sessions),
            "sessions": [
                s.summary() for s in self._sessions.values()
            ],
        }
        # Golden Signals (ADR-0034): agregar snapshot LLM si está habilitado.
        if self._golden_signals is not None:
            summary["golden_signals"] = self._golden_signals.snapshot()
        filepath = self._export_dir / "telemetry_summary.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        return str(filepath)

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    def load_all(self) -> dict[str, SessionTelemetry]:
        """Carga todas las sesiones desde archivos JSON."""
        loaded = {}
        for fpath in self._export_dir.glob("telemetry_*.json"):
            if fpath.name == "telemetry_summary.json":
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Reconstruir SessionTelemetry desde dict
            session = SessionTelemetry(
                session_id=data["session_id"],
                task=data["task"],
                project=data.get("project", ""),
                start_time=data["start_time"],
                end_time=data["end_time"],
                status=data["status"],
                total_subtasks=data["total_subtasks"],
                total_errors=data["total_errors"],
                total_warnings=data["total_warnings"],
                agent_stats=data.get("agent_stats", {}),
            )
            # Rebuild levels
            for lvl_data in data.get("levels", []):
                level = LevelRecord(
                    level=lvl_data["level"],
                    start_time=lvl_data["start_time"],
                    end_time=lvl_data.get("end_time", 0.0),
                    status=lvl_data.get("status", "completed"),
                )
                for st in lvl_data.get("subtasks", []):
                    level.subtasks.append(SubtaskRecord(
                        subtask_id=st["subtask_id"],
                        agent=st["agent"],
                        description=st["description"],
                        status=st.get("status", "completed"),
                        error=st.get("error"),
                        warning=st.get("warning"),
                        start_time=st.get("start_time", 0.0),
                        end_time=st.get("end_time", 0.0),
                        duration_ms=st.get("duration_ms", 0.0),
                    ))
                session.levels.append(level)
            loaded[data["session_id"]] = session
        return loaded

    def clear(self) -> None:
        """Limpia todas las sesiones en memoria (sin borrar archivos)."""
        self._sessions.clear()


# ---------------------------------------------------------------------------
# Decorator para tracking automático de funciones-agente
# ---------------------------------------------------------------------------

def track_subtask(telemetry_tracker: TelemetryTracker):
    """
    Decorator que trackea automáticamente una ejecución de subtask.

    Uso:
        @track_subtask(tracker)
        def my_agent_function(session_id, ...):
            ...
    """
    def decorator(func):
        from functools import wraps

        @wraps(func)
        def wrapper(session_id: str, *args, **kwargs):
            session = telemetry_tracker.get_session(session_id)
            if not session:
                return func(session_id, *args, **kwargs)

            level_idx = len(session.levels) - 1
            level_idx = max(level_idx, 0)

            record = SubtaskRecord(
                subtask_id=func.__name__,
                agent=func.__name__.split("_")[0] if "_" in func.__name__ else func.__name__,
                description=func.__doc__ or func.__name__,
                start_time=time.time(),
            )
            try:
                result = func(session_id, *args, **kwargs)
                record.status = "success"
                record.end_time = time.time()
                record.duration_ms = record.elapsed
                return result
            except Exception as e:
                record.status = "failed"
                record.end_time = time.time()
                record.duration_ms = record.elapsed
                record.error = str(e)
                raise
            finally:
                session.record_subtask(level_idx, record)

        return wrapper
    return decorator
