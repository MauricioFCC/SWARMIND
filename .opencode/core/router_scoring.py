"""
Multi-agent pattern execution and routing rule definitions.
Extracted from router_v2.py for file size compliance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MultiAgentPattern:
    """Pattern de ejecucion multi-agente.

    Sequential: agentes en cadena, output de uno es input del siguiente.
    Parallel: agentes ejecutan en paralelo, outputs se mergean.
    Loop: agente se repite hasta que condition se cumple.
    """
    pattern_type: str  # "sequential" | "parallel" | "loop"
    agents: List[str]
    merge_strategy: str = "last"
    condition: Optional[str] = None
    max_iterations: int = 5

    def validate(self) -> bool:
        """Validate pattern configuration."""
        if self.pattern_type == "sequential" and len(self.agents) < 2:
            return False
        if self.pattern_type in ("parallel", "loop") and len(self.agents) < 1:
            return False
        return True


# Predefined patterns
MULTI_AGENT_PATTERNS: Dict[str, MultiAgentPattern] = {
    "strategy_to_deploy": MultiAgentPattern(
        pattern_type="sequential",
        agents=["quant-developer", "risk-manager", "software-engineer"],
        merge_strategy="last",
    ),
    "research_to_implement": MultiAgentPattern(
        pattern_type="sequential",
        agents=["quant-scientist", "quant-developer", "quality-gate"],
        merge_strategy="last",
    ),
    "secure_deploy": MultiAgentPattern(
        pattern_type="sequential",
        agents=["software-engineer", "security-engineer", "devops-sre"],
        merge_strategy="last",
    ),
    "compliance_review": MultiAgentPattern(
        pattern_type="parallel",
        agents=["security-engineer", "risk-manager"],
        merge_strategy="vote",
    ),
    "evolve_iteration": MultiAgentPattern(
        pattern_type="loop",
        agents=["evolve"],
        condition=r"score_improvement\s*[<]\s*0\.01|converged|no_more_improvement",
        max_iterations=10,
    ),
}


@dataclass
class RoutingRule:
    """Routing rule with keyword patterns and priorities."""
    id: str
    keywords: List[str]
    regex_patterns: List[str]
    target_agent: str
    priority: int = 1
    min_confidence: float = 0.6
    requires_context: bool = False
    escalation_path: Optional[str] = None

    def matches(self, message: str) -> Tuple[bool, float]:
        """Check if message matches this rule and compute confidence."""
        msg_lower = message.lower()
        score = 0.0
        for kw in self.keywords:
            if kw.lower() in msg_lower:
                score += 0.3
        for pattern in self.regex_patterns:
            if re.search(pattern, msg_lower, re.I):
                score += 0.5
        confidence = min(1.0, score)
        return confidence >= self.min_confidence, confidence


# Routing rules configuration
ROUTING_RULES = [
    RoutingRule(id="PM-001",
        keywords=["roadmap", "fase", "checklist", "progreso", "delega", "plan", "siguiente paso"],
        regex_patterns=[r"avance\s+\w+", r"qué\s+falta", r"plan\s+de\s+trabajo", r"delega\s+@\w+"],
        target_agent="project-manager", priority=10, min_confidence=0.5, requires_context=True),
    RoutingRule(id="QD-001",
        keywords=["estrategia", "señal", "broker", "orden", "ejecución", "ONNX", "backtest"],
        regex_patterns=[r"(buy|sell|long|short)\s+\w+", r"submit.*order", r"bracket.*oco", r"strategy.*implement"],
        target_agent="quant-developer", priority=9, min_confidence=0.6),
    RoutingRule(id="QS-001",
        keywords=["overfitting", "OOS", "sharpe", "monte carlo", "feature", "validación", "experimento", "a/b test"],
        regex_patterns=[r"validat\w*\s+model", r"train.*val.*gap", r"walk.?forward", r"deflated\s+sharpe"],
        target_agent="quant-scientist", priority=9, min_confidence=0.7, requires_context=True),
    RoutingRule(id="RM-001",
        keywords=["riesgo", "drawdown", "position sizing", "kelly", "var", "exposición", "límite"],
        regex_patterns=[r"max.*dd", r"risk\s+per\s+trade", r"circuit\s+breaker", r"position\s+size"],
        target_agent="risk-manager", priority=8, min_confidence=0.6),
    RoutingRule(id="SWE-001",
        keywords=["api", "endpoint", "deploy", "infra", "ci/cd", "docker", "kubernetes", "backend", "full-stack", "microservice"],
        regex_patterns=[r"fastapi|flask|django|express|spring", r"dockerfile", r"\.github/workflows", r"api\s+key"],
        target_agent="software-engineer", priority=8, min_confidence=0.6),
    RoutingRule(id="SEC-001",
        keywords=["seguridad", "vulnerabilidad", "penetration", "audit", "compliance", "gdpr", "regulatory"],
        regex_patterns=[r"sql\s+injection", r"xss", r"csrf", r"auth.*bypass", r"secret.*leak"],
        target_agent="security-engineer", priority=10, min_confidence=0.5),
    RoutingRule(id="EA-001",
        keywords=["arquitectura", "system design", "tecnología", "stack", "adr", "roadmap", "c4"],
        regex_patterns=[r"architecture\s+(decision|review|design)", r"system\s+design", r"c4\s+model"],
        target_agent="enterprise-architect", priority=9, min_confidence=0.6, requires_context=True),
    RoutingRule(id="AI-001",
        keywords=["machine learning", "modelo", "entrenar", "inferencia", "llm", "rag", "prompt", "fine-tuning"],
        regex_patterns=[r"machine\s+(learning|model)", r"train\s+model", r"llm\s+(rag|prompt|deploy)"],
        target_agent="ai-engineer", priority=8, min_confidence=0.6),
    RoutingRule(id="CXT-001",
        keywords=["context", "prompt", "token", "compaction", "memoria", "retrieval", "system prompt", "note taking"],
        regex_patterns=[r"context\s+(engineering|optimization|curation)", r"prompt\s+(quality|section|structure)", r"token\s+budget"],
        target_agent="context-engineer", priority=7, min_confidence=0.6, requires_context=True),
    RoutingRule(id="MCP-002",
        keywords=["tool", "mcp", "tool set", "tool design", "tool overlap", "model context protocol"],
        regex_patterns=[r"tool\s+(design|set|overlap|bloat|selection)", r"mcp\s+(server|tool|connectivity)"],
        target_agent="tool-mcp-engineer", priority=7, min_confidence=0.6),
    RoutingRule(id="FB-001",
        keywords=[], regex_patterns=[r".*"], target_agent="project-manager", priority=1, min_confidence=0.0),
]


@dataclass
class RoutingNode:
    """Node in the routing graph."""
    agent: str
    transitions: Dict[str, str]
    fallback: str = "project-manager"
    max_retries: int = 2
    timeout_seconds: int = 300


# Routing graph
ROUTING_GRAPH: Dict[str, RoutingNode] = {
    "project-manager": RoutingNode(agent="project-manager", transitions={
        "needs_implementation": "quant-developer", "needs_research": "quant-scientist",
        "needs_risk_review": "risk-manager", "needs_software": "software-engineer",
        "needs_architecture": "enterprise-architect", "needs_ai_ml": "ai-engineer",
        "security_concern": "security-engineer", "needs_evolution": "evolve",
        "done": None, "blocked": "escalate",
    }, fallback="project-manager"),
    "quant-developer": RoutingNode(agent="quant-developer", transitions={
        "needs_validation": "quant-scientist", "needs_risk_check": "risk-manager",
        "needs_software": "software-engineer", "security_issue": "security-engineer",
        "blocked": "project-manager", "done": "project-manager",
    }, fallback="project-manager"),
    "quant-scientist": RoutingNode(agent="quant-scientist", transitions={
        "needs_implementation": "quant-developer", "invalid_assumption": "project-manager",
        "needs_data": "data-architect", "needs_ai_ml": "ai-engineer", "done": "quant-developer",
    }, fallback="project-manager"),
    "risk-manager": RoutingNode(agent="risk-manager", transitions={
        "strategy_adjustment": "quant-developer", "parameters_change": "quant-scientist",
        "blocked": "project-manager", "approved": "quant-developer",
    }, fallback="project-manager"),
    "software-engineer": RoutingNode(agent="software-engineer", transitions={
        "needs_architecture": "enterprise-architect", "security_review": "security-engineer",
        "needs_ai_ml": "ai-engineer", "blocked": "project-manager", "deployed": "project-manager",
    }, fallback="project-manager"),
    "security-engineer": RoutingNode(agent="security-engineer", transitions={
        "vulnerability_found": "software-engineer", "compliance_issue": "risk-manager",
        "approved": "software-engineer", "blocked": "project-manager",
    }, fallback="project-manager", max_retries=1),
    "enterprise-architect": RoutingNode(agent="enterprise-architect", transitions={
        "needs_implementation": "software-engineer", "needs_ai_ml": "ai-engineer",
        "needs_data": "data-architect", "blocked": "project-manager", "reviewed": "project-manager",
    }, fallback="project-manager"),
    "ai-engineer": RoutingNode(agent="ai-engineer", transitions={
        "needs_deployment": "software-engineer", "needs_data": "data-architect",
        "needs_validation": "quant-scientist", "blocked": "project-manager", "deployed": "project-manager",
    }, fallback="project-manager"),
    "evolve": RoutingNode(agent="evolve", transitions={
        "needs_software": "software-engineer", "needs_validation": "quant-scientist",
        "snapshot_promoted": "project-manager", "blocked": "project-manager", "done": "project-manager",
    }, fallback="project-manager"),
    "context-engineer": RoutingNode(agent="context-engineer", transitions={
        "needs_review": "quality-gate", "needs_tool_design": "tool-mcp-engineer",
        "implementation": "software-engineer", "blocked": "project-manager", "done": "project-manager",
    }, fallback="project-manager"),
    "tool-mcp-engineer": RoutingNode(agent="tool-mcp-engineer", transitions={
        "needs_review": "quality-gate", "needs_context": "context-engineer",
        "implementation": "software-engineer", "blocked": "project-manager", "done": "project-manager",
    }, fallback="project-manager"),
}


def execute_sequential_pattern(pattern: MultiAgentPattern, user_message: str,
                                context: Dict, orchestrator: 'Orchestrator') -> Dict[str, Any]:
    """Execute agents sequentially. Output of N is input of N+1."""
    trace_id = None
    accumulated_output = user_message
    chain = []
    for agent in pattern.agents:
        ctx = {**context, "previous_output": accumulated_output}
        response = orchestrator.process(accumulated_output, context_override=ctx)
        trace_id = response.get("trace_id", trace_id)
        chain.append(agent)
        accumulated_output = response.get("output", accumulated_output)
    return {
        "pattern": "sequential", "agents_executed": chain,
        "final_output": accumulated_output, "trace_id": trace_id, "status": "complete",
    }


def execute_parallel_pattern(pattern: MultiAgentPattern, user_message: str,
                              context: Dict, orchestrator: 'Orchestrator') -> Dict[str, Any]:
    """Execute agents in parallel. Merge outputs according to strategy."""
    import concurrent.futures
    outputs = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(pattern.agents)) as executor:
        futures = {
            executor.submit(orchestrator.process, user_message, context_override=context): agent
            for agent in pattern.agents
        }
        for future in concurrent.futures.as_completed(futures):
            agent = futures[future]
            try:
                outputs[agent] = future.result()
            except Exception as e:
                outputs[agent] = {"error": str(e)}
    merged = {}
    if pattern.merge_strategy == "last":
        merged = outputs.get(pattern.agents[-1], {})
    elif pattern.merge_strategy == "concat":
        merged = {"combined": [outputs.get(a, {}) for a in pattern.agents]}
    elif pattern.merge_strategy == "vote":
        approvals = sum(1 for o in outputs.values() if o.get("allowed", True))
        merged = {
            "approved": approvals >= len(pattern.agents) / 2,
            "total_votes": len(pattern.agents), "approvals": approvals,
            "individual": outputs,
        }
    return {
        "pattern": "parallel", "agents_executed": pattern.agents,
        "merged_output": merged, "status": "complete",
    }


def execute_loop_pattern(pattern: MultiAgentPattern, user_message: str,
                          context: Dict, orchestrator: 'Orchestrator') -> Dict[str, Any]:
    """Execute agent in loop until condition or max_iterations."""
    iteration = 0
    last_output = user_message
    history = []
    while iteration < pattern.max_iterations:
        response = orchestrator.process(last_output, context_override=context)
        last_output = response.get("output", str(response))
        history.append({"iteration": iteration, "output_summary": last_output[:200]})
        iteration += 1
        if pattern.condition and re.search(pattern.condition, last_output, re.I):
            break
    return {
        "pattern": "loop", "agent": pattern.agents[0] if pattern.agents else "unknown",
        "iterations": iteration, "max_iterations": pattern.max_iterations,
        "converged": iteration < pattern.max_iterations, "history": history,
        "final_output": last_output,
        "status": "converged" if iteration < pattern.max_iterations else "max_iterations_reached",
    }
