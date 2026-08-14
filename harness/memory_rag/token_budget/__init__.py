"""Token Budget — Priority-weighted, confidence-gated token budget governance.

Este paquete reemplaza al modulo ``token_budget.py`` (regla AGR: archivo
< 500 lineas). Todos los simbolos publicos del modulo original se
re-exportan desde aqui, por lo que los imports existentes
(``from harness.memory_rag.token_budget import TokenBudget``) siguen
funcionando identicos y los parches de tests que apuntan a
``harness.memory_rag.token_budget.X`` siguen afectando al paquete.

Basado en las mejores practicas 2026 de optimizacion de tokens para
sistemas multi-agente:
  - Per-agent/session budget con pesos de prioridad
  - Confidence-gated spending: detener gasto cuando la confianza es alta
  - Redistribución dinámica: el presupuesto no usado fluye a agentes de mayor prioridad
  - Múltiples pools de tokens (system, user, rag, tool_output, skill)

Ahorro estimado: 30-50% de tokens en sesiones multi-agente.
"""
from __future__ import annotations

import logging

from .constants import (
    ALL_POOLS,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    DEFAULT_AGENT_BUDGET,
    DEFAULT_POOL_ALLOCATION,
    DEFAULT_SESSION_BUDGET,
    MIN_RESERVE_TOKENS,
    POOL_CONVERSATION,
    POOL_RAG,
    POOL_SKILL,
    POOL_SYSTEM,
    POOL_TOOL_OUTPUT,
    POOL_USER,
    PRIORITY_BACKGROUND,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
)
from .manager import BudgetManager, _token_budget_manager_instance, get_token_budget_manager
from .pools import TokenBudget, TokenPool

logger = logging.getLogger("harness.memory_rag.token_budget")

__all__ = [
    "ALL_POOLS",
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "DEFAULT_AGENT_BUDGET",
    "DEFAULT_POOL_ALLOCATION",
    "DEFAULT_SESSION_BUDGET",
    "MIN_RESERVE_TOKENS",
    "POOL_CONVERSATION",
    "POOL_RAG",
    "POOL_SKILL",
    "POOL_SYSTEM",
    "POOL_TOOL_OUTPUT",
    "POOL_USER",
    "PRIORITY_BACKGROUND",
    "PRIORITY_CRITICAL",
    "PRIORITY_HIGH",
    "PRIORITY_LOW",
    "PRIORITY_NORMAL",
    "BudgetManager",
    "TokenBudget",
    "TokenPool",
    "_token_budget_manager_instance",
    "get_token_budget_manager",
    "logger",
]
