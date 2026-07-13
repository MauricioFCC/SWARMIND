"""
Stateful Graph-Based Router with confidence thresholds, fallback & escalation.
Enterprise orchestration pattern for multi-agent AI systems.

Re-exports from router_a2a and router_scoring for backward compatibility
while keeping the Orchestrator class and unique enums/dataclasses here.
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from .router_a2a import (
    A2ACard,
    A2ADiscoveryRecord,
    A2AHandoffRequest,
    A2AHandoffResponse,
    A2ARegistry,
    DEFAULT_A2A_CARDS,
    a2a_registry,
    init_default_a2a_registry,
)
from .router_scoring import (
    MULTI_AGENT_PATTERNS,
    ROUTING_GRAPH,
    ROUTING_RULES,
    MultiAgentPattern,
    RoutingNode,
    RoutingRule,
    execute_loop_pattern,
    execute_parallel_pattern,
    execute_sequential_pattern,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & TRACING — uniquely defined here
# =============================================================================


class AgentState(Enum):
    """Estados del ciclo de vida de una solicitud."""
    ROUTING = auto()
    VALIDATING = auto()
    EXECUTING = auto()
    REVIEWING = auto()
    ESCALATING = auto()
    COMPLETE = auto()
    FAILED = auto()


class ConfidenceLevel(Enum):
    """Niveles de confianza para decisiones de enrutamiento."""
    LOW = 0.0
    MEDIUM = 0.5
    HIGH = 0.8
    VERY_HIGH = 0.95


@dataclass
class ExecutionTrace:
    """Traza de ejecución para observabilidad y debugging."""
    trace_id: str
    user_message: str
    start_time: float
    agent_chain: List[str] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    guardrail_results: List[Dict] = field(default_factory=list)
    token_usage: Dict[str, int] = field(default_factory=dict)
    final_state: AgentState = AgentState.ROUTING

    def add_decision(self, agent: str, reason: str, confidence: float):
        """Register a routing decision."""
        self.decisions.append({
            "timestamp": time.time(),
            "agent": agent,
            "reason": reason,
            "confidence": confidence
        })
        self.agent_chain.append(agent)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize trace to dictionary."""
        return {
            "trace_id": self.trace_id,
            "duration_ms": (time.time() - self.start_time) * 1000,
            "agent_chain": self.agent_chain,
            "decisions": self.decisions,
            "final_state": self.final_state.name,
            "token_usage": self.token_usage
        }


# =============================================================================
# ORCHESTRATOR — core routing engine
# =============================================================================


class Orchestrator:
    """Orquestador principal con estado, observabilidad y escalación."""

    def __init__(self, config: Optional[Dict] = None):
        """Initialize with optional configuration."""
        self.config = config or {}
        self.active_traces: Dict[str, ExecutionTrace] = {}
        self._rules = sorted(ROUTING_RULES, key=lambda r: -r.priority)

    def _generate_trace_id(self, message: str) -> str:
        """Generate unique trace ID for observability."""
        timestamp = datetime.now().isoformat()
        content = f"{message}{timestamp}{time.time()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _detect_intent(self, message: str) -> Tuple[str, float, str]:
        """
        Detect message intent and select target agent.

        Returns:
            Tuple[agent_name, confidence, matched_rule_id]
        """
        for rule in self._rules:
            matches, confidence = rule.matches(message)
            if matches:
                return rule.target_agent, confidence, rule.id
        return "project-manager", 0.0, "FB-001"

    def _build_context(self, message: str, trace: ExecutionTrace) -> Dict[str, Any]:
        """Build enriched context for the target agent."""
        return {
            "user_message": message,
            "trace_id": trace.trace_id,
            "agent_chain": trace.agent_chain,
            "project_config": self.config.get("project", {}),
            "active_symbols": self.config.get("symbols", []),
            "platform": self.config.get("platform", ""),
            "risk_limits": self.config.get("risk", {}),
            "previous_decisions": trace.decisions[-3:],
        }

    def process(self, user_message: str, context_override: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Process a user message and determine the action to take.

        Args:
            user_message: The user's input message
            context_override: Optional additional context

        Returns:
            Structured response dict for the agent system
        """
        trace = ExecutionTrace(
            trace_id=self._generate_trace_id(user_message),
            user_message=user_message,
            start_time=time.time()
        )
        self.active_traces[trace.trace_id] = trace

        target_agent, confidence, rule_id = self._detect_intent(user_message)
        trace.add_decision(target_agent, f"Rule: {rule_id}", confidence)

        if confidence < ConfidenceLevel.MEDIUM.value:
            trace.add_decision("project-manager", "Baja confianza, requiere clarificación", confidence)
            return self._build_escalation_response(trace, user_message, confidence)

        base_context = self._build_context(user_message, trace)
        if context_override:
            base_context.update(context_override)

        node = ROUTING_GRAPH.get(target_agent, ROUTING_GRAPH["project-manager"])

        response = {
            "trace_id": trace.trace_id,
            "agent": target_agent,
            "state": AgentState.ROUTING.name,
            "confidence": confidence,
            "context": base_context,
            "transitions": list(node.transitions.keys()),
            "metadata": {
                "rule_matched": rule_id,
                "timestamp": datetime.now().isoformat(),
                "requires_guardrails": self.config.get("enable_guardrails", True)
            }
        }

        return response

    def _build_escalation_response(self, trace: ExecutionTrace,
                                   message: str, confidence: float) -> Dict[str, Any]:
        """Build escalation response routing to project-manager."""
        return {
            "trace_id": trace.trace_id,
            "agent": "project-manager",
            "state": AgentState.ESCALATING.name,
            "escalation_reason": "Baja confianza en enrutamiento",
            "confidence": confidence,
            "suggested_clarification": [
                "¿Podrías especificar qué aspecto necesitas trabajar?",
                "¿Se trata de implementación, investigación, riesgo o infraestructura?"
            ],
            "context": self._build_context(message, trace),
            "metadata": {
                "escalated": True,
                "original_intent_confidence": confidence
            }
        }

    def transition(self, trace_id: str, condition: str,
                   output: str, context: Dict) -> Optional[Dict[str, Any]]:
        """
        Process a transition based on the current agent's condition.

        Args:
            trace_id: Active trace ID
            condition: Transition condition
            output: Agent output
            context: Updated context

        Returns:
            Next-action dict or None if completed
        """
        trace = self.active_traces.get(trace_id)
        if not trace:
            return None

        current_agent = trace.agent_chain[-1] if trace.agent_chain else "project-manager"
        node = ROUTING_GRAPH.get(current_agent)

        if not node:
            trace.final_state = AgentState.FAILED
            return {"error": f"Agente desconocido: {current_agent}"}

        next_agent = node.transitions.get(condition, node.fallback)

        if next_agent is None:
            trace.final_state = AgentState.COMPLETE
            return {
                "status": "complete",
                "trace": trace.to_dict(),
                "summary": "Flujo completado exitosamente"
            }

        if next_agent == "escalate":
            trace.final_state = AgentState.ESCALATING
            return {
                "status": "escalate",
                "to": "project-manager",
                "reason": condition,
                "trace": trace.to_dict()
            }

        # Check A2A registry for agent availability
        target_record = a2a_registry.get_agent(next_agent)
        if target_record and not target_record.is_healthy():
            alternatives = a2a_registry.discover_by_capability(current_agent + "_handoff")
            alt_agent = alternatives[0].agent_name if alternatives else "project-manager"
            trace.add_decision(alt_agent, f"A2A fallback: {next_agent} unhealthy, routing to {alt_agent}", 0.7)
            return {
                "status": "continue",
                "agent": alt_agent,
                "context": {**context, "previous_agent": current_agent,
                            "a2a_fallback_from": next_agent,
                            "a2a_fallback_reason": f"{next_agent} is {target_record.health_status}"},
                "trace_id": trace_id
            }

        # Log A2A handoff for observability
        if next_agent in a2a_registry.list_agents():
            a2a_registry.handoff(A2AHandoffRequest(
                from_agent=current_agent,
                to_agent=next_agent,
                trace_id=trace_id,
                payload={"context": context},
            ))

        trace.add_decision(next_agent, f"Transition: {condition}", 1.0)

        return {
            "status": "continue",
            "agent": next_agent,
            "context": {**context, "previous_agent": current_agent},
            "trace_id": trace_id
        }

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Get complete trace for debugging/observability."""
        trace = self.active_traces.get(trace_id)
        return trace.to_dict() if trace else None

    def cleanup_trace(self, trace_id: str, max_age_hours: int = 24):
        """Clean old traces for memory management."""
        cutoff = time.time() - (max_age_hours * 3600)
        to_remove = [
            tid for tid, trace in self.active_traces.items()
            if trace.start_time < cutoff or tid == trace_id
        ]
        for tid in to_remove:
            del self.active_traces[tid]

    # ------------------------------------------------------------------
    # A2A Protocol Integration — Agent Discovery & Handoff
    # ------------------------------------------------------------------

    def a2a_discover(self, capability: str, min_trust: str = "internal") -> List[Dict[str, Any]]:
        """Discover agents by capability using the A2A registry."""
        records = a2a_registry.discover_by_capability(capability, min_trust)
        return [r.card.to_dict() for r in records]

    def a2a_handoff(self, from_agent: str, to_agent: str, trace_id: str,
                    payload: Dict[str, Any], priority: int = 1) -> A2AHandoffResponse:
        """Initiate a formal A2A handoff between agents."""
        request = A2AHandoffRequest(
            from_agent=from_agent, to_agent=to_agent, trace_id=trace_id,
            payload=payload, priority=priority,
        )
        return a2a_registry.handoff(request)

    def a2a_register_card(self, card: A2ACard) -> bool:
        """Register an agent's capability card (e.g., for custom agents)."""
        return a2a_registry.register(card)

    def a2a_get_registry_summary(self) -> Dict[str, Any]:
        """Get A2A registry health and discovery summary."""
        return a2a_registry.get_registry_summary()


# =============================================================================
# GLOBAL INSTANCE & HELPERS
# =============================================================================


def _load_project_config() -> Dict[str, Any]:
    """Load config from project_config.yaml with fallback to generic defaults."""
    import os
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "project_config.yaml"
    )
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        domain = raw.get("DOMAIN", "generic")
        domain_cfg = raw.get(domain.upper(), {})
        return {
            "enable_guardrails": True,
            "enable_observability": True,
            "project": {
                "name": raw.get("PROJECT_NAME", "unnamed-project"),
                "version": raw.get("PROJECT_VERSION", "1.0.0"),
                "domain": domain,
            },
            "symbols": domain_cfg.get("active_symbols", []) if isinstance(domain_cfg, dict) else [],
            "platform": domain_cfg.get("platform", "") if isinstance(domain_cfg, dict) else "",
            "risk": domain_cfg.get("risk", {}) if isinstance(domain_cfg, dict) else {},
        }
    except (FileNotFoundError, ImportError):
        return {
            "enable_guardrails": True,
            "enable_observability": True,
            "project": {"name": "project", "version": "1.0.0", "domain": "generic"},
            "symbols": [],
            "platform": "",
            "risk": {},
        }


orchestrator = Orchestrator(config=_load_project_config())


def route_message(user_message: str, **kwargs) -> Dict[str, Any]:
    """Helper function for quick message routing."""
    return orchestrator.process(user_message, context_override=kwargs)


def get_agent_prompt(agent: str, user_message: str, context: Dict) -> str:
    """
    Build optimized prompt for a specific agent.
    (Integration with prompt_optimizer)
    """
    from .prompt_optimizer import build_optimized_prompt
    return build_optimized_prompt(
        agent_role=agent, user_message=user_message,
        context=context, budget_tokens=2048
    )


# Re-export all public symbols from extracted modules for backward compatibility
# (already imported at top — they are available as module attributes)
