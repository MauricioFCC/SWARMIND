"""Consultas y reportes KPI (extraccion mecanica).

Mixin privado con rankings de agentes y skills, historial de
sesiones y resumen ejecutivo para dashboard.
"""
from __future__ import annotations

import json
import logging

import numpy as np

from .constants import (
    COLL_AGENT_PERFORMANCE,
    COLL_SESSION_KPIS,
    COLL_SKILL_EFFECTIVENESS,
)

logger = logging.getLogger(__name__)


class _ReportingMixin:
    """Metodos de consulta/reporte de AgentKpiTracker."""
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
