"""Delegation engine for the project-manager agent.

Reads tasks from TaskManager, maps task types to agent roles,
and routes messages using @rol syntax or YAML routing rules.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from harness.orchestrator.task_manager import TaskManager


_DEFAULT_CAPABILITIES: Dict[str, List[str]] = {
    "project-manager": ["plan", "delegate", "track_progress", "report", "coordinate"],
    "quant-developer": ["strategy_implementation", "order_execution", "broker_integration", "onnx_runtime"],
    "quant-scientist": ["research", "validation", "experiment_design", "feature_engineering", "oos_testing"],
    "risk-manager": ["risk_assessment", "position_sizing", "kelly_criterion", "drawdown_tracking"],
    "software-engineer": ["api_development", "full_stack", "microservices", "ci_cd", "software_design", "testing"],
    "security-engineer": ["security_audit", "vulnerability_scan", "compliance_check", "threat_modeling"],
    "enterprise-architect": ["system_design", "architecture_review", "adr", "c4_modeling", "technology_evaluation"],
    "ai-engineer": ["ml_pipeline", "model_training", "llm_ops", "inference_optimization", "feature_engineering"],
    "data-architect": ["data_modeling", "migration_design", "etl_pipeline", "schema_design"],
    "quality-gate": ["test_execution", "test_framework", "coverage_analysis", "regression_testing", "quality_gates"],
    "evolve": ["skill_evolution", "cognition_management", "experiment_analysis"],
    "frontend-engineer": ["ui_development", "dashboard", "visualization", "real_time_updates"],
    "trading-operations": ["trading_monitoring", "alert_management", "schedule_management", "connection_monitoring"],
    "mobile-engineer": ["mobile_development", "push_notifications", "offline_sync", "mobile_ui"],
    "devops-sre": ["ci_cd_pipeline", "docker_kubernetes", "monitoring", "incident_response"],
    "documentation-specialist": ["documentation", "technical_writing", "api_docs", "tutorials"],
    "requirements-analyst": ["requirements_analysis", "feasibility_study", "proposal_generation"],
    "context-engineer": ["context_engineering", "prompt_optimization", "token_budget_management"],
    "tool-mcp-engineer": ["tool_design", "mcp_server_management", "tool_set_optimization"],
}

_DEFAULT_DOMAIN_MAP: Dict[str, str] = {
    "quantitative-analysis": "quantitative-analysis",
    "risk-management": "risk-management",
    "trading": "trading",
    "architecture": "enterprise-architect",
    "ai-ml": "ai-engineer",
    "universal": "project-manager",
}

_DEFAULT_INTENT_AGENTS: Dict[str, str] = {
    "feature": "requirements-analyst",
    "implement": "requirements-analyst",
    "requirement": "requirements-analyst",
    "roadmap": "project-manager",
    "plan": "project-manager",
    "delegate": "project-manager",
    "commit": "quality-gate",
    "api": "software-engineer",
    "endpoint": "software-engineer",
    "ui": "frontend-engineer",
    "frontend": "frontend-engineer",
    "schema": "data-architect",
    "migration": "data-architect",
    "deploy": "devops-sre",
    "docker": "devops-sre",
    "security": "security-engineer",
    "vulnerability": "security-engineer",
    "mobile": "mobile-engineer",
    "ios": "mobile-engineer",
    "android": "mobile-engineer",
    "documentation": "documentation-specialist",
    "readme": "documentation-specialist",
    "strategy": "quant-developer",
    "signal": "quant-developer",
    "order": "quant-developer",
    "backtest": "quant-developer",
    "experiment": "quant-scientist",
    "validation": "quant-scientist",
    "risk": "risk-manager",
    "exposure": "risk-manager",
    "architecture": "enterprise-architect",
    "system design": "enterprise-architect",
    "machine learning": "ai-engineer",
    "model": "ai-engineer",
    "live": "trading-operations",
    "monitoring": "trading-operations",
    "evolve": "evolve",
    "self-improve": "evolve",
}


def _find_routing_rules_path() -> str:
    base = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    candidate = os.path.join(base, ".opencode", "config", "routing_rules.yaml")
    if os.path.isfile(candidate):
        return candidate
    return ""


def _load_yaml_rules(path: str) -> Dict[str, Any]:
    if not HAS_YAML:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data
    except (FileNotFoundError, yaml.YAMLError):
        return {}


class DelegationEngine:
    """Maps tasks and messages to the appropriate agent role.

    Loads routing rules from .opencode/config/routing_rules.yaml and
    integrates with the Router v2 logic when available.
    """

    def __init__(self, task_manager: Optional[TaskManager] = None) -> None:
        self._task_manager: Optional[TaskManager] = task_manager
        self._routing_rules: Dict[str, Any] = {}
        self._intent_map: Dict[str, str] = dict(_DEFAULT_INTENT_AGENTS)
        self._domain_map: Dict[str, str] = dict(_DEFAULT_DOMAIN_MAP)
        self._capabilities: Dict[str, List[str]] = {
            k: list(v) for k, v in _DEFAULT_CAPABILITIES.items()
        }
        self._router_v2: Any = None

        self._load_config()
        self._try_import_router_v2()

    def _load_config(self) -> None:
        rules_path = _find_routing_rules_path()
        if not rules_path:
            return

        data = _load_yaml_rules(rules_path)
        if not data:
            return

        self._routing_rules = data

        routing = data.get("routing_rules", data)
        if isinstance(routing, dict):
            intent_rules = routing.get("intent_routing", [])
            for rule in intent_rules:
                agent = rule.get("target_agent", "")
                keywords = rule.get("keywords", [])
                for kw in keywords:
                    self._intent_map[kw.lower()] = agent

            domain_routes = routing.get("domain_routes", [])
            for route in domain_routes:
                domain = route.get("domain", "")
                agents = route.get("agents", [])
                if agents:
                    self._domain_map[domain] = agents[0]

            departments = data.get("departments", {})
            for dept_name, dept_info in departments.items():
                head = dept_info.get("head", "")
                funciones = dept_info.get("funciones", [])
                if head and funciones:
                    if head not in self._capabilities:
                        self._capabilities[head] = []
                    for func in funciones:
                        slug = func.lower().replace(" ", "_").replace("á", "a").replace(
                            "é", "e"
                        ).replace("í", "i").replace("ó", "o").replace("ú", "u")
                        if slug not in self._capabilities[head]:
                            self._capabilities[head].append(slug)

                miembros = dept_info.get("miembros", [])
                for miembro in miembros:
                    if miembro in self._capabilities:
                        for func in funciones:
                            slug = func.lower().replace(" ", "_").replace("á", "a").replace(
                                "é", "e"
                            ).replace("í", "i").replace("ó", "o").replace("ú", "u")
                            if slug not in self._capabilities[miembro]:
                                self._capabilities[miembro].append(slug)

    def _try_import_router_v2(self) -> None:
        try:
            from opencode.core import router_v2  # type: ignore
            self._router_v2 = router_v2
        except ImportError:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            try:
                from opencode.core import router_v2  # type: ignore
                self._router_v2 = router_v2
            except ImportError:
                pass

    def delegate(self, task: Any) -> str:
        """Assign a task to the most appropriate agent based on its content.

        Args:
            task: A Task object (or dict-like) with at least title and description.

        Returns:
            The agent name (string) that the task was delegated to.
        """
        title = ""
        description = ""
        if hasattr(task, "to_dict"):
            data = task.to_dict()
            title = data.get("title", "")
            description = data.get("description", "")
        elif isinstance(task, dict):
            title = task.get("title", "")
            description = task.get("description", "")
        else:
            title = getattr(task, "title", "")
            description = getattr(task, "description", "")

        combined = f"{title} {description}".lower()

        agent = self._match_intent(combined)
        if agent:
            return agent

        return "project-manager"

    def _match_intent(self, text: str) -> str:
        for keyword, agent in sorted(
            self._intent_map.items(), key=lambda x: -len(x[0])
        ):
            if keyword in text:
                return agent
        return ""

    def route_message(self, message: str) -> str:
        """Parse a message for @rol syntax and find the target agent.

        Supports both '@agent-name' and '@agent name' syntax.
        Falls back to Router v2 if imported, or intent matching.
        """
        mentions = re.findall(r"@(\w[\w-]*)", message)
        if mentions:
            for mention in mentions:
                agent = self._resolve_agent_name(mention)
                if agent:
                    return agent

        if self._router_v2 is not None:
            try:
                result = self._router_v2.route_message(message)
                if isinstance(result, dict):
                    return result.get("agent", "project-manager")
                return result
            except Exception:
                pass

        return self._match_intent(message.lower()) or "project-manager"

    def _resolve_agent_name(self, name: str) -> str:
        name_lower = name.lower().replace("-", "_")
        known = {
            "pm": "project-manager",
            "project_manager": "project-manager",
            "project-manager": "project-manager",
            "quant": "quant-developer",
            "quant_developer": "quant-developer",
            "quant_scientist": "quant-scientist",
            "scientist": "quant-scientist",
            "risk_manager": "risk-manager",
            "risk-manager": "risk-manager",
            "risk": "risk-manager",
            "software_engineer": "software-engineer",
            "software-engineer": "software-engineer",
            "swe": "software-engineer",
            "security_engineer": "security-engineer",
            "security-engineer": "security-engineer",
            "sec": "security-engineer",
            "enterprise_architect": "enterprise-architect",
            "enterprise-architect": "enterprise-architect",
            "architect": "enterprise-architect",
            "ai_engineer": "ai-engineer",
            "ai-engineer": "ai-engineer",
            "data_architect": "data-architect",
            "data-architect": "data-architect",
            "quality_gate": "quality-gate",
            "quality-gate": "quality-gate",
            "qa": "quality-gate",
            "devops_sre": "devops-sre",
            "devops-sre": "devops-sre",
            "devops": "devops-sre",
            "frontend_engineer": "frontend-engineer",
            "frontend-engineer": "frontend-engineer",
            "frontend": "frontend-engineer",
            "mobile_engineer": "mobile-engineer",
            "mobile-engineer": "mobile-engineer",
            "trading_operations": "trading-operations",
            "trading-operations": "trading-operations",
            "ops": "trading-operations",
            "documentation_specialist": "documentation-specialist",
            "documentation-specialist": "documentation-specialist",
            "docs": "documentation-specialist",
            "requirements_analyst": "requirements-analyst",
            "requirements-analyst": "requirements-analyst",
            "ra": "requirements-analyst",
            "context_engineer": "context-engineer",
            "context-engineer": "context-engineer",
            "tool_mcp_engineer": "tool-mcp-engineer",
            "tool-mcp-engineer": "tool-mcp-engineer",
            "mcp": "tool-mcp-engineer",
        }
        return known.get(name_lower, "")

    def get_agent_capabilities(self) -> Dict[str, List[str]]:
        """Return a dict mapping each agent name to its list of capabilities."""
        return {k: list(v) for k, v in self._capabilities.items()}

    def get_agent_for_domain(self, domain: str) -> str:
        """Return the primary agent responsible for a given domain."""
        return self._domain_map.get(domain, "project-manager")

    def list_agents(self) -> List[str]:
        """Return the list of all known agent names."""
        return sorted(self._capabilities.keys())

    def set_task_manager(self, task_manager: TaskManager) -> None:
        """Attach a TaskManager instance after construction."""
        self._task_manager = task_manager
