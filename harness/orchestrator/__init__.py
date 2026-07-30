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
    # Agent Capsules (arXiv:2605.00410)
    "AgentCapsule": "harness.orchestrator.agent_capsules",
    "AgentCall": "harness.orchestrator.agent_capsules",
    "CapsuleResult": "harness.orchestrator.agent_capsules",
    "FusionStrategy": "harness.orchestrator.agent_capsules",
    # Natural Language Tools (arXiv:2607.03953)
    "NaturalLanguageToolkit": "harness.orchestrator.natural_language_tools",
    "NLTool": "harness.orchestrator.natural_language_tools",
    "NLTResult": "harness.orchestrator.natural_language_tools",
    # Multi-User Governance (arXiv:2606.21856)
    "MultiUserGovernance": "harness.orchestrator.multi_user_governance",
    "Role": "harness.orchestrator.multi_user_governance",
    "User": "harness.orchestrator.multi_user_governance",
    "AuditEntry": "harness.orchestrator.multi_user_governance",
    "ExecutionHooks": "harness.orchestrator.multi_user_governance",
    # Organizational Science (arXiv:2607.25446)
    "OrganizationalLayer": "harness.orchestrator.organizational_layer",
    "BelbinRole": "harness.orchestrator.organizational_layer",
    "RACIMatrix": "harness.orchestrator.organizational_layer",
    "MintzbergCoordination": "harness.orchestrator.organizational_layer",
    "CollaborationProtocol": "harness.orchestrator.organizational_layer",
    "TeamSpec": "harness.orchestrator.organizational_layer",
    # MetaClaw (ADR-0010, S26)
    "MetaClaw": "harness.orchestrator.metaclaw",
    "ToolRecord": "harness.orchestrator.metaclaw",
    "SelectionRecord": "harness.orchestrator.metaclaw",
    # MARS Scheduler (ADR-0010, C26)
    "MARSScheduler": "harness.orchestrator.mars_scheduler",
    "AgentProfile": "harness.orchestrator.mars_scheduler",
    "TaskSpec": "harness.orchestrator.mars_scheduler",
    "Assignment": "harness.orchestrator.mars_scheduler",
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
