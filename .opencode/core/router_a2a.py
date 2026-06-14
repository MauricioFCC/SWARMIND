"""
A2A Protocol — Agent-to-Agent Discovery & Handoff.
Implements the Agent-to-Agent (A2A) standard for autonomous agent discovery,
capability advertisement, and formal handoff between agents.

Extracted from router_v2.py for file size compliance.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class A2ACard:
    """Agent capability card — what this agent can do, how to reach it."""
    agent_name: str
    version: str = "1.0.0"
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    input_schema: str = "text/markdown"
    output_schema: str = "text/markdown"
    trust_level: str = "internal"  # internal, partner, external
    rate_limit: int = 100
    endpoint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """To dict."""
        return {
            "agent_name": self.agent_name, "version": self.version,
            "description": self.description, "capabilities": self.capabilities,
            "input_schema": self.input_schema, "output_schema": self.output_schema,
            "trust_level": self.trust_level, "rate_limit": self.rate_limit,
            "endpoint": self.endpoint,
        }


@dataclass
class A2ADiscoveryRecord:
    """Record of a discovered agent in the A2A registry."""
    agent_name: str
    card: A2ACard
    discovered_at: float = 0.0
    last_seen: float = 0.0
    health_status: str = "unknown"  # unknown, healthy, degraded, down

    def is_healthy(self) -> bool:
        """Check if agent is healthy."""
        return self.health_status in ("healthy", "unknown")


@dataclass
class A2AHandoffRequest:
    """Formal handoff request from one agent to another."""
    from_agent: str
    to_agent: str
    trace_id: str
    payload: Dict[str, Any]
    context: Dict[str, Any] = field(default_factory=dict)
    priority: int = 1  # 1=normal, 2=urgent, 3=critical
    timeout_seconds: int = 300

    def to_dict(self) -> Dict[str, Any]:
        """To dict."""
        return {
            "from_agent": self.from_agent, "to_agent": self.to_agent,
            "trace_id": self.trace_id, "priority": self.priority,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class A2AHandoffResponse:
    """Response to a handoff request."""
    accepted: bool
    trace_id: str
    reason: str = ""
    result: Optional[Dict[str, Any]] = None
    suggested_alternative: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """To dict."""
        return {
            "accepted": self.accepted, "trace_id": self.trace_id,
            "reason": self.reason, "suggested_alternative": self.suggested_alternative,
        }


class A2ARegistry:
    """Agent-to-Agent discovery registry.

    Maintains capability cards for all agents in the system and provides
    discovery lookup based on capability, trust level, or agent name.
    """

    def __init__(self):
        """Initialize empty registry."""
        self._agents: Dict[str, A2ADiscoveryRecord] = {}
        self._discovery_log: List[Dict] = []

    def register(self, card: A2ACard) -> bool:
        """Register or update an agent's capability card."""
        now = time.time()
        if card.agent_name in self._agents:
            existing = self._agents[card.agent_name]
            existing.card = card
            existing.last_seen = now
        else:
            self._agents[card.agent_name] = A2ADiscoveryRecord(
                agent_name=card.agent_name, card=card,
                discovered_at=now, last_seen=now,
            )
        self._discovery_log.append({"action": "register", "agent": card.agent_name, "timestamp": now})
        return True

    def discover_by_capability(self, capability: str, min_trust: str = "internal") -> List[A2ADiscoveryRecord]:
        """Find agents that advertise a specific capability."""
        trust_levels = {"internal": 0, "partner": 1, "external": 2}
        min_level = trust_levels.get(min_trust, 0)
        results = []
        for record in self._agents.values():
            if not record.is_healthy():
                continue
            level = trust_levels.get(record.card.trust_level, 99)
            if level > min_level:
                continue
            if any(capability.lower() in cap.lower() for cap in record.card.capabilities):
                results.append(record)
        return results

    def get_agent(self, name: str) -> Optional[A2ADiscoveryRecord]:
        """Get agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> List[str]:
        """List all registered agent names."""
        return list(self._agents.keys())

    def health_check(self, agent_name: str, status: str) -> None:
        """Update health status for an agent."""
        record = self._agents.get(agent_name)
        if record:
            record.health_status = status
            record.last_seen = time.time()

    def handoff(self, request: A2AHandoffRequest) -> A2AHandoffResponse:
        """Execute a formal handoff between agents."""
        target = self._agents.get(request.to_agent)
        if not target:
            alternatives = self.discover_by_capability("", "internal")
            alt_names = [r.agent_name for r in alternatives[:3]]
            return A2AHandoffResponse(
                accepted=False, trace_id=request.trace_id,
                reason=f"Agent '{request.to_agent}' not registered in A2A registry",
                suggested_alternative=alt_names[0] if alt_names else "project-manager",
            )
        if not target.is_healthy():
            return A2AHandoffResponse(
                accepted=False, trace_id=request.trace_id,
                reason=f"Agent '{request.to_agent}' is {target.health_status}",
                suggested_alternative="project-manager",
            )
        self._discovery_log.append({
            "action": "handoff", "from": request.from_agent, "to": request.to_agent,
            "trace_id": request.trace_id, "priority": request.priority, "timestamp": time.time(),
        })
        return A2AHandoffResponse(
            accepted=True, trace_id=request.trace_id,
            reason=f"Handoff accepted: {request.from_agent} -> {request.to_agent}",
        )

    def get_registry_summary(self) -> Dict[str, Any]:
        """Get registry summary."""
        return {
            "total_agents": len(self._agents),
            "agents": {n: {
                "capabilities": r.card.capabilities[:5],
                "trust_level": r.card.trust_level, "health": r.health_status,
            } for n, r in self._agents.items()},
            "total_handoffs": sum(1 for l in self._discovery_log if l["action"] == "handoff"),
        }


# Default A2A cards for built-in agents
DEFAULT_A2A_CARDS = [
    A2ACard(agent_name="project-manager", description="Workflow orchestration and delegation",
            capabilities=["plan", "delegate", "track_progress", "report", "coordinate"], trust_level="internal"),
    A2ACard(agent_name="quant-developer", description="Strategy implementation and broker execution",
            capabilities=["strategy_implementation", "order_execution", "broker_integration", "ONNX_runtime"], trust_level="internal"),
    A2ACard(agent_name="quant-scientist", description="Research, validation, and experiment design",
            capabilities=["research", "validation", "experiment_design", "feature_engineering", "OOS_testing"], trust_level="internal"),
    A2ACard(agent_name="risk-manager", description="Risk assessment and position sizing",
            capabilities=["risk_assessment", "position_sizing", "kelly_criterion", "drawdown_tracking"], trust_level="internal"),
    A2ACard(agent_name="software-engineer", description="Full-stack software development, APIs, services",
            capabilities=["api_development", "full_stack", "microservices", "ci_cd", "software_design", "testing"], trust_level="internal"),
    A2ACard(agent_name="security-engineer", description="Security auditing and compliance",
            capabilities=["security_audit", "vulnerability_scan", "compliance_check", "threat_modeling"], trust_level="internal"),
    A2ACard(agent_name="enterprise-architect", description="Strategic system design, architecture decisions, technology roadmaps",
            capabilities=["system_design", "architecture_review", "adr", "c4_modeling", "technology_evaluation"], trust_level="internal"),
    A2ACard(agent_name="ai-engineer", description="ML/AI engineering, LLMOps, model deployment and optimization",
            capabilities=["ml_pipeline", "model_training", "llm_ops", "inference_optimization", "feature_engineering", "experiment_tracking"], trust_level="internal"),
    A2ACard(agent_name="data-architect", description="Data modeling and pipeline design",
            capabilities=["data_modeling", "migration_design", "etl_pipeline", "schema_design"], trust_level="internal"),
    A2ACard(agent_name="quality-gate", description="Quality assurance: test strategy, gates, coverage, pre-commit validation",
            capabilities=["test_execution", "test_framework", "coverage_analysis", "regression_testing", "quality_gates", "test_strategy"], trust_level="internal"),
    A2ACard(agent_name="evolve", description="Continuous self-improvement and skill evolution",
            capabilities=["skill_evolution", "cognition_management", "experiment_analysis"], trust_level="internal"),
    A2ACard(agent_name="frontend-engineer", description="Dashboard and visualization development",
            capabilities=["ui_development", "dashboard", "visualization", "real_time_updates"], trust_level="internal"),
    A2ACard(agent_name="trading-operations", description="Live trading monitoring and alerts",
            capabilities=["trading_monitoring", "alert_management", "schedule_management", "connection_monitoring"], trust_level="internal"),
    A2ACard(agent_name="mobile-engineer", description="Mobile app development for iOS/Android",
            capabilities=["mobile_development", "push_notifications", "offline_sync", "mobile_ui"], trust_level="internal"),
    A2ACard(agent_name="devops-sre", description="CI/CD, infrastructure, and observability",
            capabilities=["ci_cd_pipeline", "docker_kubernetes", "monitoring", "incident_response"], trust_level="internal"),
    A2ACard(agent_name="documentation-specialist", description="Technical writing and knowledge base",
            capabilities=["documentation", "technical_writing", "api_docs", "tutorials"], trust_level="internal"),
    A2ACard(agent_name="requirements-analyst", description="Requirements analysis and feasibility",
            capabilities=["requirements_analysis", "feasibility_study", "proposal_generation"], trust_level="internal"),
    A2ACard(agent_name="domain-expert", description="Domain-specific knowledge and guidance",
            capabilities=["domain_knowledge", "best_practices", "technical_guidance"], trust_level="partner"),
]


def init_default_a2a_registry() -> A2ARegistry:
    """Initialize the A2A registry with all built-in agent cards."""
    registry = A2ARegistry()
    for card in DEFAULT_A2A_CARDS:
        registry.register(card)
    return registry


# Global A2A registry instance
a2a_registry = init_default_a2a_registry()
