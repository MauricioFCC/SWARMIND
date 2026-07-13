"""
Onyx-Quan-AIBot Core Framework
Enterprise-grade skill orchestration system with guardrails, routing & optimization.
"""
from .registry import SkillRegistry, SkillContract, registry
from .guardrails import GuardrailPipeline, guardrails
from .router_v2 import Orchestrator, ROUTING_GRAPH, AgentState
from .prompt_optimizer import build_optimized_prompt, compress_text, estimate_tokens

__version__ = "2.0.0"
__all__ = [
    "registry", "guardrails", "Orchestrator", "ROUTING_GRAPH", "AgentState",
    "build_optimized_prompt", "compress_text", "estimate_tokens",
    "SkillRegistry", "SkillContract", "GuardrailPipeline"
]

