"""Registros KPI (extraccion mecanica).

Dataclasses de rendimiento de agentes, efectividad de skills,
eventos de telemetria y KPIs agregados por sesion.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class AgentPerformanceRecord:
    """Registro de rendimiento de un agente en una sesión."""
    session_id: str
    agent_name: str
    task: str = ""
    subtask_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_duration_ms: float = 0.0
    avg_latency_ms: float = 0.0
    success_rate: float = 1.0
    tokens_input: int = 0
    tokens_output: int = 0
    pipeline_type: str = ""
    complexity_score: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_lancedb_row(self) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "task": self.task,
            "subtask_count": self.subtask_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "success_rate": round(self.success_rate, 4),
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "pipeline_type": self.pipeline_type,
            "complexity_score": round(self.complexity_score, 3),
            "metadata": json.dumps(self.metadata),
            "created_at": datetime.now(UTC).isoformat(),
        }

@dataclass
class SkillEffectivenessRecord:
    """Registro de efectividad de un skill."""
    skill_name: str
    domain: str
    agent: str = ""
    use_count: int = 0
    success_rate: float = 1.0
    avg_duration_ms: float = 0.0
    avg_tokens_saved: int = 0
    promotion_count: int = 0
    metadata: dict = field(default_factory=dict)

    def to_lancedb_row(self) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "skill_name": self.skill_name,
            "domain": self.domain,
            "agent": self.agent,
            "use_count": self.use_count,
            "success_rate": round(self.success_rate, 4),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "avg_tokens_saved": self.avg_tokens_saved,
            "promotion_count": self.promotion_count,
            "last_used": datetime.now(UTC).isoformat(),
            "metadata": json.dumps(self.metadata),
            "created_at": datetime.now(UTC).isoformat(),
        }

@dataclass
class TelemetryEventRecord:
    """Registro de un evento de telemetría."""
    event_type: str
    session_id: str = ""
    agent: str = ""
    level: str = "info"
    message: str = ""
    duration_ms: float = 0.0
    status: str = "success"
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_lancedb_row(self) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "event_type": self.event_type,
            "session_id": self.session_id,
            "agent": self.agent,
            "level": self.level,
            "message": self.message[:500],
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "tags": json.dumps(self.tags),
            "metadata": json.dumps(self.metadata),
            "created_at": datetime.now(UTC).isoformat(),
        }

@dataclass
class SessionKPIRecord:
    """KPIs agregados de una sesión completa."""
    session_id: str
    task: str = ""
    project: str = ""
    status: str = "completed"
    total_duration_ms: float = 0.0
    total_subtasks: int = 0
    total_errors: int = 0
    total_warnings: int = 0
    success_rate: float = 1.0
    levels_completed: int = 0
    agents_involved: int = 0
    pipeline_type: str = ""
    complexity: str = ""
    metadata: dict = field(default_factory=dict)

    def to_lancedb_row(self) -> dict:
        now = datetime.now(UTC).isoformat()
        return {
            "id": str(uuid.uuid4()),
            "session_id": self.session_id,
            "task": self.task[:200],
            "project": self.project,
            "status": self.status,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "total_subtasks": self.total_subtasks,
            "total_errors": self.total_errors,
            "total_warnings": self.total_warnings,
            "success_rate": round(self.success_rate, 4),
            "levels_completed": self.levels_completed,
            "agents_involved": self.agents_involved,
            "pipeline_type": self.pipeline_type,
            "complexity": self.complexity,
            "metadata": json.dumps(self.metadata),
            "created_at": now,
            "updated_at": now,
        }
