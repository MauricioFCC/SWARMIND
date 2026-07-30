"""
Agent KPI Tracker â€” registra mÃ©tricas de rendimiento de agentes y skills
directamente en LanceDB para anÃ¡lisis y mejora continua.

Integra con:
  - TelemetryTracker (harness/orchestrator/telemetry.py)
  - LanceVectorStore (harness/memory_rag/lance_vector_store.py)
  - MemoryConfig (harness/memory_rag/memory_config.py)

Colecciones LanceDB utilizadas:
  - agent_performance: mÃ©tricas por agente por sesiÃ³n
  - skill_effectiveness: efectividad de skills
  - telemetry_events: eventos de telemetrÃ­a
  - session_kpis: KPIs agregados por sesiÃ³n
  - agent_interactions: interacciones entre agentes
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from harness.memory_rag.lance_vector_store import LanceVectorStore
from harness.memory_rag.memory_config import (
    MemoryConfig,
    TelemetryLevel,
    get_memory_config,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants â€” nombres de colecciones KPI
# ---------------------------------------------------------------------------

COLL_AGENT_PERFORMANCE = "agent_performance"
COLL_SKILL_EFFECTIVENESS = "skill_effectiveness"
COLL_TELEMETRY_EVENTS = "telemetry_events"
COLL_SESSION_KPIS = "session_kpis"
COLL_AGENT_INTERACTIONS = "agent_interactions"

ALL_KPI_COLLECTIONS = [
    COLL_AGENT_PERFORMANCE,
    COLL_SKILL_EFFECTIVENESS,
    COLL_TELEMETRY_EVENTS,
    COLL_SESSION_KPIS,
    COLL_AGENT_INTERACTIONS,
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AgentPerformanceRecord:
    """Registro de rendimiento de un agente en una sesiÃ³n."""
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
            "created_at": datetime.now(timezone.utc).isoformat(),
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
            "last_used": datetime.now(timezone.utc).isoformat(),
            "metadata": json.dumps(self.metadata),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }


@dataclass
class TelemetryEventRecord:
    """Registro de un evento de telemetrÃ­a."""
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
            "created_at": datetime.now(timezone.utc).isoformat(),
        }


@dataclass
class SessionKPIRecord:
    """KPIs agregados de una sesiÃ³n completa."""
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
        now = datetime.now(timezone.utc).isoformat()
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


# ---------------------------------------------------------------------------
# AgentKpiTracker
# ---------------------------------------------------------------------------

class AgentKpiTracker:
    """
    Tracker de KPIs que persiste mÃ©tricas de rendimiento en LanceDB.

    Uso:
        tracker = AgentKpiTracker(store=vector_store)
        
        # Registrar rendimiento de agente
        tracker.record_agent_performance(
            session_id="ses-001",
            agent_name="builder",
            subtask_count=5,
            success_count=4,
            error_count=1,
            total_duration_ms=12000.0,
        )
        
        # Registrar evento de telemetrÃ­a
        tracker.record_telemetry_event(
            event_type="plan_created",
            session_id="ses-001",
            agent="planner",
            duration_ms=450.0,
        )
        
        # Finalizar sesiÃ³n â†’ genera KPIs agregados
        tracker.finalize_session_kpi(
            session_id="ses-001",
            task="implementar API",
            total_duration_ms=150000.0,
            total_subtasks=5,
            total_errors=1,
        )
    """

    def __init__(
        self,
        store: LanceVectorStore | None = None,
        config: MemoryConfig | None = None,
    ) -> None:
        """
        Args:
            store: LanceVectorStore instance. Si es None, crea uno con config.
            config: MemoryConfig. Si es None, usa get_memory_config().
        """
        self._config = config or get_memory_config()

        if store:
            self._store = store
        else:
            from harness.memory_rag.lance_vector_store import LanceVectorStore
            self._store = LanceVectorStore(
                db_path=self._config.lancedb_path,
                allow_fallback=self._config.allow_fallback,
            )

        self._ensure_collections()

        self._enabled = self._config.telemetry_level != TelemetryLevel.OFF
        self._full_telemetry = self._config.telemetry_level == TelemetryLevel.FULL

        logger.info(
            "AgentKpiTracker initialized | backend=%s | telemetry=%s | full=%s",
            self._config.backend.value,
            self._config.telemetry_level.value,
            self._full_telemetry,
        )

    def _ensure_collections(self) -> None:
        """Asegura que las colecciones KPI existan."""
        existing = set(self._store.list_collections())
        for coll in ALL_KPI_COLLECTIONS:
            if coll not in existing:
                try:
                    self._store.create_collection(coll)
                    logger.info("Created KPI collection '%s'", coll)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Could not create collection '%s': %s", coll, e)

    # ------------------------------------------------------------------
    # Agent Performance
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Skill Effectiveness
    # ------------------------------------------------------------------

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
                "last_used": datetime.now(timezone.utc).isoformat(),
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

    # ------------------------------------------------------------------
    # Telemetry Events
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Session KPIs
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Agent Interactions
    # ------------------------------------------------------------------

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
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return self._insert(COLL_AGENT_INTERACTIONS, row)

    # ------------------------------------------------------------------
    # Query / Reporting
    # ------------------------------------------------------------------

    def get_agent_rankings(
        self, top_n: int = 10, min_sessions: int = 1,
    ) -> list[dict]:
        """
        Obtiene ranking de agentes por success_rate.

        Returns:
            Lista de dicts con: agent_name, avg_success_rate, total_sessions, ...
        """
        try:
            results = self._store.search(
                COLL_AGENT_PERFORMANCE,
                query_vector=np.zeros(self._config.embedding_dim, dtype=np.float32),
                top_k=100,
            )
        except Exception:  # noqa: BLE001
            return []

        # Aggregate by agent
        agent_stats: dict[str, dict] = {}
        for r in results:
            meta = r.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    meta = {}

            name = r.get("agent_name", meta.get("agent_name", "unknown"))
            if name not in agent_stats:
                agent_stats[name] = {
                    "agent_name": name,
                    "total_sessions": 0,
                    "total_subtasks": 0,
                    "total_success": 0,
                    "total_errors": 0,
                    "total_duration_ms": 0.0,
                }
            s = agent_stats[name]
            s["total_sessions"] += 1
            s["total_subtasks"] += r.get("subtask_count", 0)
            s["total_success"] += r.get("success_count", 0)
            s["total_errors"] += r.get("error_count", 0)
            s["total_duration_ms"] += r.get("total_duration_ms", 0.0)

        # Compute averages
        rankings = []
        for name, stats in agent_stats.items():
            total = stats["total_subtasks"]
            rankings.append({
                "agent_name": name,
                "total_sessions": stats["total_sessions"],
                "total_subtasks": stats["total_subtasks"],
                "success_rate": round(
                    stats["total_success"] / total, 4
                ) if total > 0 else 0.0,
                "error_rate": round(
                    stats["total_errors"] / total, 4
                ) if total > 0 else 0.0,
                "avg_duration_per_session_ms": round(
                    stats["total_duration_ms"] / stats["total_sessions"], 2
                ) if stats["total_sessions"] > 0 else 0.0,
            })

        rankings.sort(key=lambda x: x["success_rate"], reverse=True)
        return [r for r in rankings if r["total_sessions"] >= min_sessions][:top_n]

    def get_skill_rankings(self, top_n: int = 10) -> list[dict]:
        """
        Obtiene ranking de skills por uso y efectividad.

        Returns:
            Lista de dicts con: skill_name, domain, use_count, success_rate, ...
        """
        try:
            results = self._store.search(
                COLL_SKILL_EFFECTIVENESS,
                query_vector=np.zeros(self._config.embedding_dim, dtype=np.float32),
                top_k=100,
            )
        except Exception:  # noqa: BLE001
            return []

        rankings = []
        for r in results:
            meta = r.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    meta = {}

            rankings.append({
                "skill_name": r.get("skill_name", meta.get("skill_name", "")),
                "domain": r.get("domain", meta.get("domain", "")),
                "agent": r.get("agent", meta.get("agent", "")),
                "use_count": r.get("use_count", 0),
                "success_rate": r.get("success_rate", 0.0),
                "avg_duration_ms": r.get("avg_duration_ms", 0.0),
                "promotion_count": r.get("promotion_count", 0),
            })

        rankings.sort(key=lambda x: x["use_count"], reverse=True)
        return rankings[:top_n]

    def get_session_history(
        self, limit: int = 20, status: str | None = None,
    ) -> list[dict]:
        """
        Obtiene historial de sesiones con sus KPIs.

        Args:
            limit: MÃ¡ximo de sesiones a retornar.
            status: Filtrar por estado ("completed", "failed", etc.).

        Returns:
            Lista de dicts con KPIs de sesiÃ³n.
        """
        try:
            results = self._store.search(
                COLL_SESSION_KPIS,
                query_vector=np.zeros(self._config.embedding_dim, dtype=np.float32),
                top_k=limit * 2,
            )
        except Exception:  # noqa: BLE001
            return []

        sessions = []
        for r in results:
            if status and r.get("status", "") != status:
                continue
            meta = r.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    meta = {}
            sessions.append({
                "session_id": r.get("session_id", ""),
                "task": r.get("task", ""),
                "project": r.get("project", ""),
                "status": r.get("status", ""),
                "total_duration_ms": r.get("total_duration_ms", 0.0),
                "total_subtasks": r.get("total_subtasks", 0),
                "total_errors": r.get("total_errors", 0),
                "success_rate": r.get("success_rate", 0.0),
                "levels_completed": r.get("levels_completed", 0),
                "agents_involved": r.get("agents_involved", 0),
                "complexity": r.get("complexity", ""),
            })

        sessions.sort(key=lambda x: x.get("total_duration_ms", 0), reverse=True)
        return sessions[:limit]

    def get_dashboard_summary(self) -> dict:
        """
        Obtiene un resumen ejecutivo para dashboard.

        Returns:
            Dict con mÃ©tricas globales del sistema.
        """
        agent_rankings = self.get_agent_rankings(top_n=5)
        skill_rankings = self.get_skill_rankings(top_n=5)
        recent_sessions = self.get_session_history(limit=5)

        return {
            "total_agents_tracked": len(agent_rankings),
            "top_agents": agent_rankings[:3],
            "total_skills_tracked": len(skill_rankings),
            "top_skills": skill_rankings[:3],
            "recent_sessions": recent_sessions,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _insert(self, collection: str, row: dict) -> str | None:
        """Inserta una fila en LanceDB como vector de ceros (bÃºsqueda por metadata)."""
        try:
            # Use zero vector for metadata-only records
            vec = np.zeros(self._config.embedding_dim, dtype=np.float32)
            ids = self._store.insert(collection, vec.reshape(1, -1), [row])
            return ids[0] if ids else None
        except Exception as e:  # noqa: BLE001
            logger.warning("KPI insert error in %s: %s", collection, e)
            return None
