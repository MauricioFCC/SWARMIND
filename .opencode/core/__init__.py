"""
trading-bot-AIBot Core Framework
Enterprise-grade skill orchestration system with guardrails, routing & optimization.
"""
from .guardrails import GuardrailPipeline, guardrails
from .prompt_optimizer import build_optimized_prompt, compress_text, estimate_tokens
from .registry import SkillContract, SkillRegistry, registry
from .router_v2 import ROUTING_GRAPH, AgentState, Orchestrator

__version__ = "2.0.0"
__all__ = [
    "ROUTING_GRAPH",
    "AgentState",
    "GuardrailPipeline",
    "Orchestrator",
    "SkillContract",
    "SkillRegistry",
    "build_optimized_prompt",
    "compress_text",
    "estimate_tokens",
    "guardrails",
    "registry"
]

