"""
Model Router — Hybrid local/cloud model routing for agent tasks.
Routes simple tasks to local Ollama models, complex tasks to cloud APIs.

Features:
  - Multi-Provider Abstraction: OpenAI, Anthropic, Google, Mistral, DeepSeek
  - Failover automático entre proveedores
  - Load balancing round-robin por tier
  - Health checks periódicos
  - Cost tracking por proveedor y proyecto
  - Latencia P50/P95/P99 por proveedor
  - Control de presupuesto por proyecto
"""

from .router import (
    BudgetLimit,
    ExecutionResult,
    ModelRouter,
    MultiAPIProvider,
    ProviderConfig,
    ProviderHealth,
    ProviderStatus,
    ProviderTier,
    RoutingDecision,
)

__all__ = [
    "BudgetLimit",
    "ExecutionResult",
    "ModelRouter",
    "MultiAPIProvider",
    "ProviderConfig",
    "ProviderHealth",
    "ProviderStatus",
    "ProviderTier",
    "RoutingDecision",
]
