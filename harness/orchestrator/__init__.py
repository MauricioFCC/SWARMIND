"""
Orquestador multi-agente: lazy loading via __getattr__ (PEP 562).

Exporta las clases principales del modulo de orquestacion con carga perezosa.
Cold-start: ~1ms vs ~500ms con imports eager.
"""
from __future__ import annotations

import importlib
from typing import Any

_SYMBOL_MAP: dict[str, str] = {
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
    # Automated Red-Teaming (ADR-0033, Fase 3.2)
    "AttackVector": "harness.orchestrator.red_teamer",
    "RedTeamFinding": "harness.orchestrator.red_teamer",
    "RedTeamer": "harness.orchestrator.red_teamer",
    # Decision Trace + Resilience Governance (ADR-0033, OmniRoute)
    "DecisionRecord": "harness.orchestrator.decision_trace",
    "DecisionTrace": "harness.orchestrator.decision_trace",
    "format_decision_header": "harness.orchestrator.decision_trace",
    "ConnectionCooldown": "harness.orchestrator.resilience_governance",
    "ModelLockout": "harness.orchestrator.resilience_governance",
    "ResilienceGovernance": "harness.orchestrator.resilience_governance",
    # Agentic Trajectory Evaluator (ADR-0033, Fase 3.1)
    "TrajectoryStep": "harness.orchestrator.trajectory_evaluator",
    "TrajectoryReport": "harness.orchestrator.trajectory_evaluator",
    "TrajectoryEvaluator": "harness.orchestrator.trajectory_evaluator",
    "build_judge_prompt": "harness.orchestrator.trajectory_evaluator",
    # Continuous Verification post-deploy (ADR-0033, Fase 3.3)
    "MetricSample": "harness.orchestrator.continuous_verifier",
    "VerificationResult": "harness.orchestrator.continuous_verifier",
    "ContinuousVerifier": "harness.orchestrator.continuous_verifier",
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
