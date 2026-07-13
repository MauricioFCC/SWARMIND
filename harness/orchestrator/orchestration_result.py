"""
Resultado de orquestación para el Task Orchestrator.

Define OrchestratorResult, el dataclass que encapsula todo lo que el LLM
necesita para ejecutar: el plan, nivel actual, resultados previos,
asignaciones de agentes e historial de comunicación.

Uso:
    result = OrchestratorResult(
        session_id="abc-123",
        target_agent="coder",
        plan=plan,
        current_level=[...],
        previous_results=[...],
        ...
    )
    data = result.to_dict()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from harness.orchestrator.task_planner import TaskPlan


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class OrchestratorResult:
    """
    Result of processing a message through the orchestrator.

    Contains everything the LLM needs to execute: the plan, current level,
    previous results, agent assignments, and communication history.
    """
    session_id: str
    target_agent: str           # Primary agent for this dispatch
    plan: TaskPlan
    current_level: List[Dict]    # Subtasks ready for execution
    previous_results: List[Dict] # Completed subtask results
    session_status: str          # Human-readable status
    communication_log: List[Dict] # Recent agent communications
    original_message: str
    is_new_plan: bool            # Whether a new plan was created
    is_complete: bool            # Whether the entire plan is done
    is_debate: bool = False      # Whether this task uses debate strategy
    debate_agents: List[str] = field(default_factory=list)  # Agents in the debate
    debate_strategy: str = ""    # The debate strategy to use

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "target_agent": self.target_agent,
            "plan": self.plan.to_dict(),
            "current_level": self.current_level,
            "previous_results": self.previous_results,
            "session_status": self.session_status,
            "communication_log": self.communication_log,
            "original_message": self.original_message,
            "is_new_plan": self.is_new_plan,
            "is_complete": self.is_complete,
            "is_debate": self.is_debate,
            "debate_agents": list(self.debate_agents),
            "debate_strategy": self.debate_strategy,
        }


__all__ = ["OrchestratorResult"]
