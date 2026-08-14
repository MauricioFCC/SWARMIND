"""Estructuras de datos del planner — ``SubTask`` y ``TaskPlan`` (DAG).

Extracción mecánica desde ``harness/orchestrator/task_planner.py``
(sin cambios de lógica).

El logger se resuelve vía el paquete en tiempo de llamada
(``import harness.orchestrator.task_planner as _pkg``) manteniendo el nombre
de logger original ``harness.orchestrator.task_planner``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import harness.orchestrator.task_planner as _pkg


@dataclass
class SubTask:
    """A single atomic subtask in the execution plan."""
    id: str
    agent: str          # builder | scientist | guardian | evolve | coordinator
    description: str
    dependencies: list[str] = field(default_factory=list)
    expected_output: str = ""
    context_hint: str = ""
    completed: bool = False
    result: str = ""
    confidence_impact: str = "neutral"  # "critical" | "neutral" | "validation"
    estimated_latency_ms: float | None = None  # Peso para ruta crítica (LAMaS, ADR-0034)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "description": self.description,
            "dependencies": list(self.dependencies),
            "expected_output": self.expected_output,
            "context_hint": self.context_hint,
            "completed": self.completed,
            "result": self.result,
            "confidence_impact": self.confidence_impact,
        }


@dataclass
class TaskPlan:
    """A complete execution plan with DAG structure."""
    session_id: str
    original_message: str
    subtasks: list[SubTask] = field(default_factory=list)
    template_name: str = ""  # Which template was used to create this plan

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "original_message": self.original_message,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "template_name": self.template_name,
        }

    def get_levels(self) -> list[list[SubTask]]:
        """
        Group subtasks into execution levels (topological sort).

        Level 0: no dependencies (run in PARALLEL)
        Level 1: depend on level 0
        Level 2: depend on level 1
        etc.

        LAMaS-lite (ADR-0034): dentro de cada nivel, las subtasks de la ruta
        crítica se ordenan primero para reducir el tiempo end-to-end sin
        violar dependencias.
        """
        remaining = {s.id: s for s in self.subtasks}
        completed_ids: set = set()
        levels: list[list[SubTask]] = []

        while remaining:
            level = [
                s for s in remaining.values()
                if all(dep in completed_ids for dep in s.dependencies)
            ]
            if not level:
                # Circular dependency — break it by adding all remaining
                level = list(remaining.values())
                _pkg.logger.warning(
                    "Circular dependency detected in plan %s. "
                    "Breaking by adding %d remaining subtasks.",
                    self.session_id, len(level),
                )
            levels.append(self._order_level(level))
            for s in level:
                del remaining[s.id]
                completed_ids.add(s.id)

        return levels

    def _order_level(self, level: list[SubTask]) -> list[SubTask]:
        """Ordena un nivel priorizando la ruta crítica (LAMaS-lite, ADR-0034).

        Args:
            level: subtasks listas para ejecutarse en este nivel.

        Returns:
            Subtasks ordenadas: las críticas primero, el resto en orden.
        """
        if len(level) <= 1:
            return level
        try:
            from harness.orchestrator.latency_aware import CriticalPath
            return CriticalPath().optimize(level)
        except ImportError:
            # Fallback: mantener orden original si no se puede importar.
            return level

    def get_pending(self) -> list[SubTask]:
        """Get subtasks that are not yet completed and whose deps are met."""
        completed_ids = {s.id for s in self.subtasks if s.completed}
        return [
            s for s in self.subtasks
            if not s.completed
            and all(dep in completed_ids for dep in s.dependencies)
        ]

    def get_next_level(self) -> list[SubTask]:
        """Get the next level of subtasks ready for execution."""
        pending = self.get_pending()
        if not pending:
            return []
        # Group by dependency depth
        {s.id for s in self.subtasks if s.completed}
        # The ones with the shallowest dependency depth
        min_deps = min(len(s.dependencies) for s in pending)
        return [s for s in pending if len(s.dependencies) == min_deps]

    def mark_completed(self, subtask_id: str, result: str = "") -> None:
        """Mark a subtask as completed with its result."""
        for s in self.subtasks:
            if s.id == subtask_id:
                s.completed = True
                s.result = result
                _pkg.logger.info(
                    "Subtask %s (%s) completed. %d/%d done.",
                    subtask_id, s.agent,
                    sum(1 for x in self.subtasks if x.completed),
                    len(self.subtasks),
                )
                return
        _pkg.logger.warning("Subtask %s not found in plan %s.", subtask_id, self.session_id)

    def get_current_level_num(self) -> int:
        """Get the 0-based index of the current execution level.

        Recorre los niveles devueltos por get_levels() y retorna el indice
        del primer nivel que contiene subtareas sin completar.
        Si todos los niveles estan completos, retorna la cantidad de niveles
        (equivalente a "nivel finalizado").
        """
        completed_ids = {s.id for s in self.subtasks if s.completed}
        for idx, level in enumerate(self.get_levels()):
            if any(s.id not in completed_ids for s in level):
                return idx
        return len(self.get_levels())

    def is_complete(self) -> bool:
        """Check if all subtasks are complete."""
        return all(s.completed for s in self.subtasks)

    def get_summary(self) -> str:
        """Human-readable summary of plan status."""
        total = len(self.subtasks)
        done = sum(1 for s in self.subtasks if s.completed)
        lines = [
            f"📋 Plan ({done}/{total} subtasks completadas):",
        ]
        for level_idx, level in enumerate(self.get_levels()):
            is_parallel = len(level) > 1
            mode = "⚡ PARALELO" if is_parallel else "→ SECUENCIAL"
            lines.append(f"\n  Nivel {level_idx} ({mode}):")
            for s in level:
                status = "✅" if s.completed else "⏳" if s in self.get_pending() else "⏸️"
                deps_str = f" [deps: {', '.join(s.dependencies)}]" if s.dependencies else ""
                lines.append(f"    {status} [{s.agent}] {s.description}{deps_str}")
        return "\n".join(lines)
