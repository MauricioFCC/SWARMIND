"""
Stateful Graph-Based Router with confidence thresholds, fallback & escalation.
Enterprise orchestration pattern for multi-agent AI systems.
"""
import re
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any, Tuple


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
class RoutingRule:
    """Regla de enrutamiento con patrones y prioridades."""
    id: str
    keywords: List[str]
    regex_patterns: List[str]
    target_agent: str
    priority: int = 1
    min_confidence: float = 0.6
    requires_context: bool = False
    escalation_path: Optional[str] = None
    
    def matches(self, message: str) -> Tuple[bool, float]:
        """Verifica si el mensaje coincide y calcula confianza."""
        msg_lower = message.lower()
        score = 0.0
        
        # Puntuación por keywords
        for kw in self.keywords:
            if kw.lower() in msg_lower:
                score += 0.3
        
        # Puntuación por regex (más precisa)
        for pattern in self.regex_patterns:
            if re.search(pattern, msg_lower, re.I):
                score += 0.5
        
        # Normalizar a [0, 1]
        confidence = min(1.0, score)
        return confidence >= self.min_confidence, confidence


@dataclass
class RoutingNode:
    """Nodo en el grafo de enrutamiento."""
    agent: str
    transitions: Dict[str, str]  # condition -> next_agent
    fallback: str = "project-manager"
    max_retries: int = 2
    timeout_seconds: int = 300


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
        self.decisions.append({
            "timestamp": time.time(),
            "agent": agent,
            "reason": reason,
            "confidence": confidence
        })
        self.agent_chain.append(agent)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "duration_ms": (time.time() - self.start_time) * 1000,
            "agent_chain": self.agent_chain,
            "decisions": self.decisions,
            "final_state": self.final_state.name,
            "token_usage": self.token_usage
        }


# =============================================================================
# A2A PROTOCOL — Agent-to-Agent Discovery & Handoff
# =============================================================================
# Implements the Agent-to-Agent (A2A) standard for autonomous agent discovery,
# capability advertisement, and formal handoff between agents.

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
        return {
            "agent_name": self.agent_name,
            "version": self.version,
            "description": self.description,
            "capabilities": self.capabilities,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "trust_level": self.trust_level,
            "rate_limit": self.rate_limit,
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
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "trace_id": self.trace_id,
            "priority": self.priority,
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
        return {
            "accepted": self.accepted,
            "trace_id": self.trace_id,
            "reason": self.reason,
            "suggested_alternative": self.suggested_alternative,
        }


class A2ARegistry:
    """Agent-to-Agent discovery registry.

    Maintains capability cards for all agents in the system and provides
    discovery lookup based on capability, trust level, or agent name.
    """

    def __init__(self):
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
                agent_name=card.agent_name,
                card=card,
                discovered_at=now,
                last_seen=now,
            )
        self._discovery_log.append({
            "action": "register",
            "agent": card.agent_name,
            "timestamp": now,
        })
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
        return self._agents.get(name)

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())

    def health_check(self, agent_name: str, status: str):
        """Update health status for an agent."""
        record = self._agents.get(agent_name)
        if record:
            record.health_status = status
            record.last_seen = time.time()

    def handoff(self, request: A2AHandoffRequest) -> A2AHandoffResponse:
        """Execute a formal handoff between agents.

        Validates that the target agent exists, is healthy, and can handle
        the requested payload. Returns acceptance or rejection with alternative.
        """
        target = self._agents.get(request.to_agent)
        if not target:
            # Suggest nearest alternative
            alternatives = self.discover_by_capability("", "internal")
            alt_names = [r.agent_name for r in alternatives[:3]]
            return A2AHandoffResponse(
                accepted=False,
                trace_id=request.trace_id,
                reason=f"Agent '{request.to_agent}' not registered in A2A registry",
                suggested_alternative=alt_names[0] if alt_names else "project-manager",
            )
        if not target.is_healthy():
            return A2AHandoffResponse(
                accepted=False,
                trace_id=request.trace_id,
                reason=f"Agent '{request.to_agent}' is {target.health_status}",
                suggested_alternative="project-manager",
            )
        self._discovery_log.append({
            "action": "handoff",
            "from": request.from_agent,
            "to": request.to_agent,
            "trace_id": request.trace_id,
            "priority": request.priority,
            "timestamp": time.time(),
        })
        return A2AHandoffResponse(
            accepted=True,
            trace_id=request.trace_id,
            reason=f"Handoff accepted: {request.from_agent} -> {request.to_agent}",
        )

    def get_registry_summary(self) -> Dict[str, Any]:
        return {
            "total_agents": len(self._agents),
            "agents": {n: {
                "capabilities": r.card.capabilities[:5],
                "trust_level": r.card.trust_level,
                "health": r.health_status,
            } for n, r in self._agents.items()},
            "total_handoffs": sum(1 for l in self._discovery_log if l["action"] == "handoff"),
        }


# Default A2A registry with built-in agent cards
DEFAULT_A2A_CARDS = [
    A2ACard(agent_name="project-manager", description="Workflow orchestration and delegation",
            capabilities=["plan", "delegate", "track_progress", "report", "coordinate"],
            trust_level="internal"),
    A2ACard(agent_name="quant-developer", description="Strategy implementation and broker execution",
            capabilities=["strategy_implementation", "order_execution", "broker_integration", "ONNX_runtime"],
            trust_level="internal"),
    A2ACard(agent_name="quant-scientist", description="Research, validation, and experiment design",
            capabilities=["research", "validation", "experiment_design", "feature_engineering", "OOS_testing"],
            trust_level="internal"),
    A2ACard(agent_name="risk-manager", description="Risk assessment and position sizing",
            capabilities=["risk_assessment", "position_sizing", "kelly_criterion", "drawdown_tracking"],
            trust_level="internal"),
    A2ACard(agent_name="software-engineer", description="Full-stack software development, APIs, services",
            capabilities=["api_development", "full_stack", "microservices", "ci_cd", "software_design", "testing"],
            trust_level="internal"),
    A2ACard(agent_name="security-engineer", description="Security auditing and compliance",
            capabilities=["security_audit", "vulnerability_scan", "compliance_check", "threat_modeling"],
            trust_level="internal"),
    A2ACard(agent_name="enterprise-architect", description="Strategic system design, architecture decisions, technology roadmaps",
            capabilities=["system_design", "architecture_review", "adr", "c4_modeling", "technology_evaluation"],
            trust_level="internal"),
    A2ACard(agent_name="ai-engineer", description="ML/AI engineering, LLMOps, model deployment and optimization",
            capabilities=["ml_pipeline", "model_training", "llm_ops", "inference_optimization", "feature_engineering", "experiment_tracking"],
            trust_level="internal"),
    A2ACard(agent_name="data-architect", description="Data modeling and pipeline design",
            capabilities=["data_modeling", "migration_design", "etl_pipeline", "schema_design"],
            trust_level="internal"),
    A2ACard(agent_name="quality-gate", description="Quality assurance: test strategy, gates, coverage, pre-commit validation",
            capabilities=["test_execution", "test_framework", "coverage_analysis", "regression_testing", "quality_gates", "test_strategy"],
            trust_level="internal"),
    A2ACard(agent_name="evolve", description="Continuous self-improvement and skill evolution",
            capabilities=["skill_evolution", "cognition_management", "experiment_analysis"],
            trust_level="internal"),
    A2ACard(agent_name="frontend-engineer", description="Dashboard and visualization development",
            capabilities=["ui_development", "dashboard", "visualization", "real_time_updates"],
            trust_level="internal"),
    A2ACard(agent_name="trading-operations", description="Live trading monitoring and alerts",
            capabilities=["trading_monitoring", "alert_management", "schedule_management", "connection_monitoring"],
            trust_level="internal"),
    A2ACard(agent_name="mobile-engineer", description="Mobile app development for iOS/Android",
            capabilities=["mobile_development", "push_notifications", "offline_sync", "mobile_ui"],
            trust_level="internal"),
    A2ACard(agent_name="devops-sre", description="CI/CD, infrastructure, and observability",
            capabilities=["ci_cd_pipeline", "docker_kubernetes", "monitoring", "incident_response"],
            trust_level="internal"),
    A2ACard(agent_name="documentation-specialist", description="Technical writing and knowledge base",
            capabilities=["documentation", "technical_writing", "api_docs", "tutorials"],
            trust_level="internal"),
    A2ACard(agent_name="requirements-analyst", description="Requirements analysis and feasibility",
            capabilities=["requirements_analysis", "feasibility_study", "proposal_generation"],
            trust_level="internal"),
    A2ACard(agent_name="domain-expert", description="Domain-specific knowledge and guidance",
            capabilities=["domain_knowledge", "best_practices", "technical_guidance"],
            trust_level="partner"),
]


def init_default_a2a_registry() -> A2ARegistry:
    """Initialize the A2A registry with all built-in agent cards."""
    registry = A2ARegistry()
    for card in DEFAULT_A2A_CARDS:
        registry.register(card)
    return registry


# Global A2A registry instance
a2a_registry = init_default_a2a_registry()


# =============================================================================
# MULTI-AGENT PATTERNS — Sequential, Parallel, Loop
# =============================================================================

@dataclass
class MultiAgentPattern:
    """Patrón de ejecución multi-agente.
    
    Sequential: agentes en cadena, output de uno es input del siguiente.
    Parallel: agentes ejecutan en paralelo, outputs se mergean.
    Loop: agente se repite hasta que condition se cumple.
    """
    pattern_type: str  # "sequential" | "parallel" | "loop"
    agents: List[str]
    merge_strategy: str = "last"  # sequential: last, parallel: concat|vote|priority, loop: condition
    condition: Optional[str] = None  # loop: condición de salida (regex sobre output)
    max_iterations: int = 5

    def validate(self) -> bool:
        if self.pattern_type == "sequential" and len(self.agents) < 2:
            return False
        if self.pattern_type in ("parallel", "loop") and len(self.agents) < 1:
            return False
        return True


# Patrones predefinidos
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


def execute_sequential_pattern(pattern: MultiAgentPattern, user_message: str,
                                context: Dict, orchestrator: 'Orchestrator') -> Dict[str, Any]:
    """Ejecuta agentes en secuencia. Output de N es input de N+1."""
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
        "pattern": "sequential",
        "agents_executed": chain,
        "final_output": accumulated_output,
        "trace_id": trace_id,
        "status": "complete",
    }


def execute_parallel_pattern(pattern: MultiAgentPattern, user_message: str,
                              context: Dict, orchestrator: 'Orchestrator') -> Dict[str, Any]:
    """Ejecuta agentes en paralelo. Mergea outputs según estrategia."""
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
        # Voto mayoritario simple: contar agentes que aprueban/rechazan
        approvals = sum(1 for o in outputs.values() if o.get("allowed", True))
        merged = {
            "approved": approvals >= len(pattern.agents) / 2,
            "total_votes": len(pattern.agents),
            "approvals": approvals,
            "individual": outputs,
        }

    return {
        "pattern": "parallel",
        "agents_executed": pattern.agents,
        "merged_output": merged,
        "status": "complete",
    }


def execute_loop_pattern(pattern: MultiAgentPattern, user_message: str,
                          context: Dict, orchestrator: 'Orchestrator') -> Dict[str, Any]:
    """Ejecuta agente en loop hasta condición o max_iterations."""
    iteration = 0
    last_output = user_message
    history = []

    while iteration < pattern.max_iterations:
        response = orchestrator.process(last_output, context_override=context)
        last_output = response.get("output", str(response))
        history.append({
            "iteration": iteration,
            "output_summary": last_output[:200],
        })
        iteration += 1

        # Verificar condición de salida
        if pattern.condition and re.search(pattern.condition, last_output, re.I):
            break

    return {
        "pattern": "loop",
        "agent": pattern.agents[0] if pattern.agents else "unknown",
        "iterations": iteration,
        "max_iterations": pattern.max_iterations,
        "converged": iteration < pattern.max_iterations,
        "history": history,
        "final_output": last_output,
        "status": "converged" if iteration < pattern.max_iterations else "max_iterations_reached",
    }


# =============================================================================
# REGLAS DE ENRUTAMIENTO CONFIGURABLES
# =============================================================================

ROUTING_RULES = [
    # Project Manager - Alta prioridad para coordinación
    RoutingRule(
        id="PM-001",
        keywords=["roadmap", "fase", "checklist", "progreso", "delega", "plan", "siguiente paso"],
        regex_patterns=[r"avance\s+\w+", r"qué\s+falta", r"plan\s+de\s+trabajo", r"delega\s+@\w+"],
        target_agent="project-manager",
        priority=10,
        min_confidence=0.5,
        requires_context=True
    ),
    
    # Quant Developer - Estrategias y ejecución
    RoutingRule(
        id="QD-001",
        keywords=["estrategia", "señal", "broker", "orden", "ejecución", "ONNX", "backtest"],
        regex_patterns=[r"(buy|sell|long|short)\s+\w+", r"submit.*order", r"bracket.*oco", r"strategy.*implement"],
        target_agent="quant-developer",
        priority=9,
        min_confidence=0.6
    ),
    
    # Quant Scientist - Validación, investigación y experimentos
    RoutingRule(
        id="QS-001",
        keywords=["overfitting", "OOS", "sharpe", "monte carlo", "feature", "validación", "estadístico", "experimento", "a/b test", "causal", "bootstrap", "power analysis"],
        regex_patterns=[r"validat\w*\s+model", r"train.*val.*gap", r"walk.?forward", r"deflated\s+sharpe", r"a/b\s+test", r"experiment\s+design"],
        target_agent="quant-scientist",
        priority=9,
        min_confidence=0.7,
        requires_context=True
    ),
    
    # Risk Manager - Gestión de riesgo
    RoutingRule(
        id="RM-001",
        keywords=["riesgo", "drawdown", "position sizing", "kelly", "var", "exposición", "límite"],
        regex_patterns=[r"max.*dd", r"risk\s+per\s+trade", r"circuit\s+breaker", r"position\s+size"],
        target_agent="risk-manager",
        priority=8,
        min_confidence=0.6
    ),
    
    # Software Engineer - APIs, servicios, full-stack
    RoutingRule(
        id="SWE-001",
        keywords=["api", "endpoint", "deploy", "infra", "ci/cd", "docker", "kubernetes", "backend", "full-stack", "microservice"],
        regex_patterns=[r"fastapi|flask|django|express|spring", r"dockerfile", r"\.github/workflows", r"api\s+key"],
        target_agent="software-engineer",
        priority=8,
        min_confidence=0.6
    ),
    
    # Security Engineer - Seguridad y compliance
    RoutingRule(
        id="SEC-001",
        keywords=["seguridad", "vulnerabilidad", "penetration", "audit", "compliance", "gdpr", "regulatory"],
        regex_patterns=[r"sql\s+injection", r"xss", r"csrf", r"auth.*bypass", r"secret.*leak", r"compliance.*rule"],
        target_agent="security-engineer",
        priority=10,
        min_confidence=0.5
    ),
    
    # Enterprise Architect - Arquitectura y diseño de sistemas
    RoutingRule(
        id="EA-001",
        keywords=["arquitectura", "system design", "tecnología", "stack", "adr", "roadmap", "c4", "estrategia técnica"],
        regex_patterns=[r"architecture\s+(decision|review|design)", r"system\s+design", r"technology\s+(stack|selection)", r"c4\s+model"],
        target_agent="enterprise-architect",
        priority=9,
        min_confidence=0.6,
        requires_context=True
    ),
    
    # AI/ML Engineer - Modelos, pipelines, LLM
    RoutingRule(
        id="AI-001",
        keywords=["machine learning", "modelo", "entrenar", "inferencia", "llm", "rag", "prompt", "fine-tuning", "onnx", "mlflow"],
        regex_patterns=[r"machine\s+(learning|model)", r"train\s+model", r"inference\s+(optimization|pipeline)", r"llm\s+(rag|prompt|deploy)", r"feature\s+engineering"],
        target_agent="ai-engineer",
        priority=8,
        min_confidence=0.6
    ),
    
    # Context Engineer - Optimización de contexto, prompts, compactación
    RoutingRule(
        id="CXT-001",
        keywords=["context", "prompt", "token", "compaction", "memoria", "retrieval", "system prompt", "note taking", "context window", "attention budget"],
        regex_patterns=[r"context\s+(engineering|optimization|curation)", r"prompt\s+(quality|section|structure)", r"compaction\s+(strategy|fidelity)", r"just.?in.?time\s+retrieval", r"token\s+budget"],
        target_agent="context-engineer",
        priority=7,
        min_confidence=0.6,
        requires_context=True
    ),
    
    # Tool/MCP Engineer - Ecosistema de herramientas MCP
    RoutingRule(
        id="MCP-002",
        keywords=["tool", "mcp", "tool set", "tool design", "tool overlap", "herramienta", "model context protocol", "tool call", "mcp server"],
        regex_patterns=[r"tool\s+(design|set|overlap|bloat|selection)", r"mcp\s+(server|tool|connectivity|protocol)", r"model\s+context\s+protocol", r"few.?shot\s+examples?\s+(for|tool)"],
        target_agent="tool-mcp-engineer",
        priority=7,
        min_confidence=0.6
    ),
    
    # Fallback - Project Manager como coordinator
    RoutingRule(
        id="FB-001",
        keywords=[],
        regex_patterns=[r".*"],
        target_agent="project-manager",
        priority=1,
        min_confidence=0.0
    ),
]

# Grafo de transiciones entre agentes
ROUTING_GRAPH: Dict[str, RoutingNode] = {
    "project-manager": RoutingNode(
        agent="project-manager",
        transitions={
            "needs_implementation": "quant-developer",
            "needs_research": "quant-scientist",
            "needs_risk_review": "risk-manager",
            "needs_software": "software-engineer",
            "needs_architecture": "enterprise-architect",
            "needs_ai_ml": "ai-engineer",
            "security_concern": "security-engineer",
            "needs_evolution": "evolve",
            "done": None,
            "blocked": "escalate"
        },
        fallback="project-manager"
    ),
    "quant-developer": RoutingNode(
        agent="quant-developer",
        transitions={
            "needs_validation": "quant-scientist",
            "needs_risk_check": "risk-manager",
            "needs_software": "software-engineer",
            "security_issue": "security-engineer",
            "blocked": "project-manager",
            "done": "project-manager"
        },
        fallback="project-manager"
    ),
    "quant-scientist": RoutingNode(
        agent="quant-scientist",
        transitions={
            "needs_implementation": "quant-developer",
            "invalid_assumption": "project-manager",
            "needs_data": "data-architect",
            "needs_ai_ml": "ai-engineer",
            "done": "quant-developer"
        },
        fallback="project-manager"
    ),
    "risk-manager": RoutingNode(
        agent="risk-manager",
        transitions={
            "strategy_adjustment": "quant-developer",
            "parameters_change": "quant-scientist",
            "blocked": "project-manager",
            "approved": "quant-developer"
        },
        fallback="project-manager"
    ),
    "software-engineer": RoutingNode(
        agent="software-engineer",
        transitions={
            "needs_architecture": "enterprise-architect",
            "security_review": "security-engineer",
            "needs_ai_ml": "ai-engineer",
            "blocked": "project-manager",
            "deployed": "project-manager"
        },
        fallback="project-manager"
    ),
    "security-engineer": RoutingNode(
        agent="security-engineer",
        transitions={
            "vulnerability_found": "software-engineer",
            "compliance_issue": "risk-manager",
            "approved": "software-engineer",
            "blocked": "project-manager"
        },
        fallback="project-manager",
        max_retries=1
    ),
    "enterprise-architect": RoutingNode(
        agent="enterprise-architect",
        transitions={
            "needs_implementation": "software-engineer",
            "needs_ai_ml": "ai-engineer",
            "needs_data": "data-architect",
            "blocked": "project-manager",
            "reviewed": "project-manager"
        },
        fallback="project-manager"
    ),
    "ai-engineer": RoutingNode(
        agent="ai-engineer",
        transitions={
            "needs_deployment": "software-engineer",
            "needs_data": "data-architect",
            "needs_validation": "quant-scientist",
            "blocked": "project-manager",
            "deployed": "project-manager"
        },
        fallback="project-manager"
    ),
    "evolve": RoutingNode(
        agent="evolve",
        transitions={
            "needs_software": "software-engineer",
            "needs_validation": "quant-scientist",
            "snapshot_promoted": "project-manager",
            "blocked": "project-manager",
            "done": "project-manager"
        },
        fallback="project-manager"
    ),
    "context-engineer": RoutingNode(
        agent="context-engineer",
        transitions={
            "needs_review": "quality-gate",
            "needs_tool_design": "tool-mcp-engineer",
            "implementation": "software-engineer",
            "blocked": "project-manager",
            "done": "project-manager"
        },
        fallback="project-manager"
    ),
    "tool-mcp-engineer": RoutingNode(
        agent="tool-mcp-engineer",
        transitions={
            "needs_review": "quality-gate",
            "needs_context": "context-engineer",
            "implementation": "software-engineer",
            "blocked": "project-manager",
            "done": "project-manager"
        },
        fallback="project-manager"
    ),
}


class Orchestrator:
    """Orquestador principal con estado, observabilidad y escalación."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.active_traces: Dict[str, ExecutionTrace] = {}
        self._rules = sorted(ROUTING_RULES, key=lambda r: -r.priority)
        
    def _generate_trace_id(self, message: str) -> str:
        """Genera ID único para trazabilidad."""
        timestamp = datetime.now().isoformat()
        content = f"{message}{timestamp}{time.time()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _detect_intent(self, message: str) -> Tuple[str, float, str]:
        """
        Detecta la intención del mensaje y selecciona el agente.
        
        Returns:
            Tuple[agent_name, confidence, matched_rule_id]
        """
        for rule in self._rules:
            matches, confidence = rule.matches(message)
            if matches:
                return rule.target_agent, confidence, rule.id
        return "project-manager", 0.0, "FB-001"
    
    def _build_context(self, message: str, trace: ExecutionTrace) -> Dict[str, Any]:
        """Construye contexto enriquecido para el agente."""
        return {
            "user_message": message,
            "trace_id": trace.trace_id,
            "agent_chain": trace.agent_chain,
            "project_config": self.config.get("project", {}),
            "active_symbols": self.config.get("symbols", []),
            "platform": self.config.get("platform", ""),
            "risk_limits": self.config.get("risk", {}),
            "previous_decisions": trace.decisions[-3:],  # Últimas 3 decisiones
        }
    
    def process(self, user_message: str, context_override: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Procesa un mensaje del usuario y determina la acción a tomar.
        
        Args:
            user_message: Mensaje del usuario
            context_override: Contexto adicional opcional
        
        Returns:
            Dict con la respuesta estructurada para el sistema de agentes
        """
        # 1. Crear trace para observabilidad
        trace = ExecutionTrace(
            trace_id=self._generate_trace_id(user_message),
            user_message=user_message,
            start_time=time.time()
        )
        self.active_traces[trace.trace_id] = trace
        
        # 2. Detectar intención y agente objetivo
        target_agent, confidence, rule_id = self._detect_intent(user_message)
        trace.add_decision(target_agent, f"Rule: {rule_id}", confidence)
        
        # 3. Validar confianza mínima
        if confidence < ConfidenceLevel.MEDIUM.value:
            # Escalar a project-manager para clarificación
            trace.add_decision("project-manager", "Baja confianza, requiere clarificación", confidence)
            return self._build_escalation_response(trace, user_message, confidence)
        
        # 4. Construir contexto
        base_context = self._build_context(user_message, trace)
        if context_override:
            base_context.update(context_override)
        
        # 5. Obtener nodo de enrutamiento
        node = ROUTING_GRAPH.get(target_agent, ROUTING_GRAPH["project-manager"])
        
        # 6. Preparar respuesta
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
        """Construye respuesta para escalación al project-manager."""
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
        Procesa una transición basada en la condición del agente actual.
        
        Args:
            trace_id: ID de la traza activa
            condition: Condición que desencadena la transición
            output: Output generado por el agente
            context: Contexto actualizado
        
        Returns:
            Dict con la siguiente acción o None si completado
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
            # Terminal state
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
            # Agent is unhealthy, try A2A discovery for alternative
            alternatives = a2a_registry.discover_by_capability(current_agent + "_handoff")
            alt_agent = alternatives[0].agent_name if alternatives else "project-manager"
            trace.add_decision(alt_agent, f"A2A fallback: {next_agent} unhealthy, routing to {alt_agent}", 0.7)
            return {
                "status": "continue",
                "agent": alt_agent,
                "context": {**context, "previous_agent": current_agent, "a2a_fallback_from": next_agent, "a2a_fallback_reason": f"{next_agent} is {target_record.health_status}"},
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

        # Transición normal
        trace.add_decision(next_agent, f"Transition: {condition}", 1.0)
        
        return {
            "status": "continue",
            "agent": next_agent,
            "context": {**context, "previous_agent": current_agent},
            "trace_id": trace_id
        }
    
    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene la traza completa para debugging/observabilidad."""
        trace = self.active_traces.get(trace_id)
        return trace.to_dict() if trace else None
    
    def cleanup_trace(self, trace_id: str, max_age_hours: int = 24):
        """Limpia trazas antiguas para gestión de memoria."""
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
            from_agent=from_agent,
            to_agent=to_agent,
            trace_id=trace_id,
            payload=payload,
            priority=priority,
        )
        return a2a_registry.handoff(request)

    def a2a_register_card(self, card: A2ACard) -> bool:
        """Register an agent's capability card (e.g., for custom agents)."""
        return a2a_registry.register(card)

    def a2a_get_registry_summary(self) -> Dict[str, Any]:
        """Get A2A registry health and discovery summary."""
        return a2a_registry.get_registry_summary()


# Instancia global con configuración cargada desde project_config.yaml
# Si el archivo de config no existe, usa defaults genéricos.
def _load_project_config() -> Dict[str, Any]:
    """Carga config desde project_config.yaml con fallback a defaults genéricos."""
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
        # Fallback: defaults completamente genéricos
        return {
            "enable_guardrails": True,
            "enable_observability": True,
            "project": {"name": "project", "version": "1.0.0", "domain": "generic"},
            "symbols": [],
            "platform": "",
            "risk": {},
        }


orchestrator = Orchestrator(config=_load_project_config())


# Funciones de utilidad para integración rápida
def route_message(user_message: str, **kwargs) -> Dict[str, Any]:
    """Función helper para enrutamiento rápido."""
    return orchestrator.process(user_message, context_override=kwargs)


def get_agent_prompt(agent: str, user_message: str, context: Dict) -> str:
    """
    Construye el prompt optimizado para un agente específico.
    (Integración con prompt_optimizer)
    """
    from .prompt_optimizer import build_optimized_prompt
    return build_optimized_prompt(
        agent_role=agent,
        user_message=user_message,
        context=context,
        budget_tokens=2048
    )
