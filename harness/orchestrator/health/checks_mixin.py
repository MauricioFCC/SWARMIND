"""Health checks mixin — liveness y readiness de ``AgentHealthChecker``.

Extraccion mecanica del modulo original
``harness/orchestrator/health.py`` (sin cambios de logica ni firmas).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .models import HealthStatus

logger = logging.getLogger("harness.orchestrator.health")


class _ChecksMixin:
    """Mixin con los checks fisicos (liveness/readiness)."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_liveness(self) -> HealthStatus:
        """
        Nivel 1: Liveness Check.

        Verifica que el sistema base responda:
          - Importaciones basicas funcionan
          - Directorios esenciales existen
          - Modulos core cargan correctamente
        """
        issues = []

        # Check 1: imports basicos
        try:
            from harness.orchestrator.agent_bus import AgentBus  # noqa
            from harness.orchestrator.task_planner import TaskPlanner  # noqa
        except ImportError as e:
            issues.append(f"ImportError: {e}")

        # Check 2: directorios esenciales (desde harness/)
        base = Path(__file__).resolve().parent.parent.parent  # harness/
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
            details={
                "issues": issues,
                "base_path": str(base),
                "hardware": self.get_hardware_info(),
            },
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

        # Check 1: TaskPlanner basico
        try:
            from harness.orchestrator.task_planner import TaskPlanner
            planner = TaskPlanner()
            plan = planner.decompose("test health check")
            subtask_count = len(plan.subtasks)
        except Exception as e:  # noqa: BLE001
            issues.append(f"TaskPlanner error: {e}")
            subtask_count = 0

        # Check 2: Agentes disponibles
        try:
            from harness.orchestrator.agent_discovery import discover_agents_recursive
            agents = discover_agents_recursive()
            agent_count = len(agents)
        except Exception as e:  # noqa: BLE001
            issues.append(f"Agent discovery error: {e}")
            agent_count = 0

        # Check 3: LanceDB (si esta configurado)
        db_ok = False
        if self._store is not None:
            try:
                dummy_vec = np.zeros(384, dtype=np.float32)
                self._store.search("health_check", dummy_vec, top_k=1)
                db_ok = True
            except Exception as e:  # noqa: BLE001
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
