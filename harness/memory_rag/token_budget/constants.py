"""Constantes del paquete ``token_budget``.

Extraido mecanicamente de ``token_budget.py`` (regla AGR < 500 lineas).
Sin cambios de logica: los valores y nombres son identicos al original.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Token pools
POOL_SYSTEM = "system"          # System prompt, role definitions
POOL_USER = "user"              # User message
POOL_RAG = "rag"                # Retrieved context
POOL_SKILL = "skill"            # Skill descriptions
POOL_TOOL_OUTPUT = "tool_output"  # Tool call results
POOL_CONVERSATION = "conversation"  # Chat history

ALL_POOLS = [POOL_SYSTEM, POOL_USER, POOL_RAG, POOL_SKILL, POOL_TOOL_OUTPUT, POOL_CONVERSATION]

# Default budget allocation per pool (as fraction of total budget)
DEFAULT_POOL_ALLOCATION: dict[str, float] = {
    POOL_SYSTEM: 0.15,
    POOL_USER: 0.05,
    POOL_RAG: 0.30,
    POOL_SKILL: 0.15,
    POOL_TOOL_OUTPUT: 0.20,
    POOL_CONVERSATION: 0.15,
}

# Priority levels (higher = more important, gets more budget)
PRIORITY_CRITICAL = 100
PRIORITY_HIGH = 75
PRIORITY_NORMAL = 50
PRIORITY_LOW = 25
PRIORITY_BACKGROUND = 10

# Confidence thresholds
CONFIDENCE_HIGH = 0.90    # > 90% confidence → stop further spending
CONFIDENCE_MEDIUM = 0.70  # > 70% → reduce spending rate

# Default per-agent token budget (fallback plano).
# Los budgets por rol viven en el SSOT .opencode/config/token_budgets.yaml
# (ADR-0040 H6): cuando el YAML existe, TokenBudgetManager los aplica por rol
# (coordinator 4096, guardian 2048, ...) en vez de este flat 4000.
DEFAULT_AGENT_BUDGET = 4000
DEFAULT_SESSION_BUDGET = 16000
MIN_RESERVE_TOKENS = 500  # never starve an agent below this
