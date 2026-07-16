"""
Orquestador multi-agente: lazy loading via __getattr__ (PEP 562).

Exporta las clases principales del modulo de orquestacion con carga perezosa.
Cold-start: ~1ms vs ~500ms con imports eager.
"""
from __future__ import annotations
import importlib
from typing import Any, Dict

_SYMBOL_MAP: Dict[str, str] = {
    "TaskManager": "harness.orchestrator.task_manager",
    "DelegationEngine": "harness.orchestrator.delegation_engine",
    "AgentBus": "harness.orchestrator.agent_bus",
    "AgentBusError": "harness.orchestrator.agent_bus",
    "InvalidMessageError": "harness.orchestrator.agent_bus",
    "SandboxLoop": "harness.orchestrator.sandbox_loop",
    "AgentDispatcher": "harness.orchestrator.agent_dispatcher",
    "Scheduler": "harness.orchestrator.scheduler",
    "ScheduledJob": "harness.orchestrator.scheduler",
    "DebateOrchestrator": "harness.orchestrator.debate_orchestrator",
    "DebateResult": "harness.orchestrator.debate_orchestrator",
    "DebateRound": "harness.orchestrator.debate_orchestrator",
    "DebateStrategy": "harness.orchestrator.debate_orchestrator",
    # Nuevos modulos (opcionales, no se cargan hasta usarse)
    "evaluator_optimizer": "harness.orchestrator.workflow_patterns",
    "voting": "harness.orchestrator.workflow_patterns",
    "PBTTemplate": "harness.orchestrator.pbt_templates",
    "BehavioralTracer": "harness.orchestrator.behavioral_tracer",
    "check_all": "harness.orchestrator.architectural_guardrails",
}


def __getattr__(name: str) -> Any:
    """Lazy import de simbolos del paquete orchestrator."""
    module_path = _SYMBOL_MAP.get(name)
    if module_path is None:
        raise AttributeError(f"module 'harness.orchestrator' has no attribute '{name}'")
    module = importlib.import_module(module_path)
    attr = getattr(module, name, None)
    if attr is None:
        raise AttributeError(f"module '{module_path}' has no attribute '{name}'")
    globals()[name] = attr
    return attr


def __dir__() -> list:
    return list(_SYMBOL_MAP.keys())


__all__ = list(_SYMBOL_MAP.keys())
