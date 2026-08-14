"""Registro de metricas KPI (extraccion mecanica).

Mixin privado con metodos de registro: rendimiento de agentes,
efectividad de skills, eventos de telemetria, KPIs de sesion e
interacciones entre agentes.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

import numpy as np

from .constants import (
    COLL_AGENT_INTERACTIONS,
    COLL_AGENT_PERFORMANCE,
    COLL_SESSION_KPIS,
    COLL_SKILL_EFFECTIVENESS,
    COLL_TELEMETRY_EVENTS,
)
from .models import (
    AgentPerformanceRecord,
    SessionKPIRecord,
    SkillEffectivenessRecord,
    TelemetryEventRecord,
)

logger = logging.getLogger(__name__)


class _RecordingMixin:
    """Metodos de registro de metricas de AgentKpiTracker."""
    def record_agent_performance(
        self,
        session_id: str,
        agent_name: str,
        subtask_count: int = 0,
        success_count: int = 0,
        error_count: int = 0,
        total_duration_ms: float = 0.0,
        avg_latency_ms: float = 0.0,
        success_rate: float | None = None,
        tokens_input: int = 0,
        tokens_output: int = 0,
        pipeline_type: str = "",
        complexity_score: float = 0.0,
        task: str = "",
        metadata: dict | None = None,
    ) -> str | None:
        """
        Registra mÃ©tricas de rendimiento de un agente.

        Returns:
            ID del registro creado, o None si telemetrÃ­a estÃ¡ off.
        """
        if not self._enabled:
            return None

        if success_rate is None:
            success_rate = (
                success_count / subtask_count if subtask_count > 0 else 1.0
            )

        record = AgentPerformanceRecord(
            session_id=session_id,
            agent_name=agent_name,
            task=task,
            subtask_count=subtask_count,
            success_count=success_count,
            error_count=error_count,
            total_duration_ms=total_duration_ms,
            avg_latency_ms=avg_latency_ms,
            success_rate=success_rate,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            pipeline_type=pipeline_type,
            complexity_score=complexity_score,
            metadata=metadata or {},
        )

        return self._insert(COLL_AGENT_PERFORMANCE, record.to_lancedb_row())

    def record_skill_effectiveness(
        self,
        skill_name: str,
        domain: str,
        agent: str = "",
        use_count: int = 1,
        success: bool = True,
        duration_ms: float = 0.0,
        tokens_saved: int = 0,
        promoted: bool = False,
        metadata: dict | None = None,
    ) -> str | None:
        """
        Registra o actualiza mÃ©tricas de efectividad de un skill.

        Si el skill ya existe, actualiza sus mÃ©tricas acumuladas.

        Returns:
            ID del registro.
        """
        if not self._enabled:
            return None

        # Buscar si ya existe registro para este skill+agent
        existing = self._find_skill_record(skill_name, domain, agent)

        if existing:
            # Actualizar mÃ©tricas acumuladas
            existing_id = existing.get("id", "")
            meta = existing.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    meta = {}

            current_use = existing.get("use_count", 0)
            current_success = existing.get("success_rate", 1.0) * current_use

            new_use_count = current_use + 1
            new_success_count = current_success + (1 if success else 0)
            new_success_rate = new_success_count / new_use_count if new_use_count > 0 else 1.0

            # Average duration (running average)
            current_avg = existing.get("avg_duration_ms", 0.0)
            new_avg = (current_avg * current_use + duration_ms) / new_use_count

            updates = {
                "use_count": new_use_count,
                "success_rate": round(new_success_rate, 4),
                "avg_duration_ms": round(new_avg, 2),
                "avg_tokens_saved": existing.get("avg_tokens_saved", 0) + tokens_saved,
                "promotion_count": existing.get("promotion_count", 0) + (1 if promoted else 0),
                "last_used": datetime.now(UTC).isoformat(),
            }

            self._store.update_records(
                COLL_SKILL_EFFECTIVENESS,
                filters={"id": existing_id},
                updates=updates,
            )
            return existing_id

        else:
            # Crear nuevo registro
            record = SkillEffectivenessRecord(
                skill_name=skill_name,
                domain=domain,
                agent=agent,
                use_count=use_count,
                success_rate=1.0 if success else 0.0,
                avg_duration_ms=duration_ms,
                avg_tokens_saved=tokens_saved,
                promotion_count=1 if promoted else 0,
                metadata=metadata or {},
            )
            return self._insert(COLL_SKILL_EFFECTIVENESS, record.to_lancedb_row())

    def _find_skill_record(
        self, skill_name: str, domain: str, agent: str,
    ) -> dict | None:
        """Busca un registro de skill existente."""
        try:
            results = self._store.search(
                COLL_SKILL_EFFECTIVENESS,
                query_vector=np.zeros(self._config.embedding_dim, dtype=np.float32),
                top_k=20,
            )
            for r in results:
                meta = r.get("metadata", {})
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except (json.JSONDecodeError, TypeError):
                        meta = {}
                r_skill = meta.get("skill_name", r.get("skill_name", ""))
                r_domain = meta.get("domain", r.get("domain", ""))
                r_agent = meta.get("agent", r.get("agent", ""))
                if r_skill == skill_name and r_domain == domain and r_agent == agent:
                    return r
        except Exception as _exc:  # noqa: BLE001
            logger.warning("agent_kpi_tracker: %s", _exc)
        return None

    def record_telemetry_event(
        self,
        event_type: str,
        session_id: str = "",
        agent: str = "",
        level: str = "info",
        message: str = "",
        duration_ms: float = 0.0,
        status: str = "success",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> str | None:
        """
        Registra un evento de telemetrÃ­a.

        Con telemetry_level=BASIC, solo guarda eventos importantes
        (error, warning, plan_created, plan_complete).
        Con telemetry_level=FULL, guarda todos los eventos.
        """
        if not self._enabled:
            return None

        # Filtrar eventos bÃ¡sicos vs full
        if not self._full_telemetry:
            important_events = {
                "error", "warning", "plan_created", "plan_complete",
                "circuit_breaker_open", "stall_detected", "level_timeout",
                "session_failed", "session_aborted",
            }
            if event_type not in important_events and level not in ("error", "warning"):
                return None

        record = TelemetryEventRecord(
            event_type=event_type,
            session_id=session_id,
            agent=agent,
            level=level,
            message=message,
            duration_ms=duration_ms,
            status=status,
            tags=tags or [],
            metadata=metadata or {},
        )

        return self._insert(COLL_TELEMETRY_EVENTS, record.to_lancedb_row())

    def record_session_kpi(
        self,
        session_id: str,
        task: str = "",
        project: str = "",
        status: str = "completed",
        total_duration_ms: float = 0.0,
        total_subtasks: int = 0,
        total_errors: int = 0,
        total_warnings: int = 0,
        success_rate: float = 1.0,
        levels_completed: int = 0,
        agents_involved: int = 0,
        pipeline_type: str = "",
        complexity: str = "",
        metadata: dict | None = None,
    ) -> str | None:
        """
        Registra KPIs agregados de una sesiÃ³n completa.

        Si ya existe un KPI para esta session_id, lo actualiza.
        """
        if not self._enabled:
            return None

        # Check if session KPI already exists
        existing = self._find_session_kpi(session_id)

        record = SessionKPIRecord(
            session_id=session_id,
            task=task,
            project=project,
            status=status,
            total_duration_ms=total_duration_ms,
            total_subtasks=total_subtasks,
            total_errors=total_errors,
            total_warnings=total_warnings,
            success_rate=success_rate,
            levels_completed=levels_completed,
            agents_involved=agents_involved,
            pipeline_type=pipeline_type,
            complexity=complexity,
            metadata=metadata or {},
        )

        if existing:
            existing_id = existing.get("id", "")
            row = record.to_lancedb_row()
            row.pop("id", None)
            row.pop("created_at", None)
            self._store.update_records(
                COLL_SESSION_KPIS,
                filters={"id": existing_id},
                updates=row,
            )
            return existing_id
        else:
            return self._insert(COLL_SESSION_KPIS, record.to_lancedb_row())

    def _find_session_kpi(self, session_id: str) -> dict | None:
        """Busca un KPI de sesiÃ³n existente."""
        try:
            results = self._store.search(
                COLL_SESSION_KPIS,
                query_vector=np.zeros(self._config.embedding_dim, dtype=np.float32),
                top_k=10,
            )
            for r in results:
                meta = r.get("metadata", {})
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except (json.JSONDecodeError, TypeError):
                        meta = {}
                if r.get("session_id", meta.get("session_id", "")) == session_id:
                    return r
        except Exception as _exc:  # noqa: BLE001
            logger.warning("agent_kpi_tracker: %s", _exc)
        return None

    def record_agent_interaction(
        self,
        session_id: str,
        from_agent: str,
        to_agent: str,
        message_type: str = "request",
        subtask_id: str = "",
        duration_ms: float = 0.0,
        success: bool = True,
        metadata: dict | None = None,
    ) -> str | None:
        """
        Registra una interacciÃ³n entre agentes (para grafos de colaboraciÃ³n).
        """
        if not self._enabled or not self._full_telemetry:
            return None

        row = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "message_type": message_type,
            "subtask_id": subtask_id,
            "duration_ms": round(duration_ms, 2),
            "success": success,
            "metadata": json.dumps(metadata or {}),
            "created_at": datetime.now(UTC).isoformat(),
        }
        return self._insert(COLL_AGENT_INTERACTIONS, row)
