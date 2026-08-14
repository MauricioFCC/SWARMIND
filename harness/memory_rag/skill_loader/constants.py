"""Constantes del paquete ``skill_loader``.

Extraido mecanicamente de ``skill_loader.py`` (regla AGR < 500 lineas).
Sin cambios de logica: los valores y nombres son identicos al original.
"""
from __future__ import annotations

# Dominios conocidos para routing contextual
DOMAIN_KEYWORDS: dict[str, set[str]] = {
    "trading": {"trading", "quant", "market", "exchange", "broker", "order",
                "signal", "strategy", "portfolio", "risk", "alpha"},
    "healthtech": {"health", "medical", "patient", "hipaa", "fhir", "clinical",
                   "diagnosis", "hospital", "ehr", "healthcare"},
    "retail": {"retail", "pos", "inventory", "sale", "cashier",
               "product", "customer", "store", "payment"},
    "general": {"general", "system", "config", "deploy", "devops", "api"},
    "evolve": {"evolve", "improve", "optimize", "learn", "skill", "meta"},
}

# Mapa de skill -> dominio(s)
SKILL_DOMAIN_MAP: dict[str, list[str]] = {
    "evolve": ["evolve", "general"],
    "hedgefund": ["general"],
    "quant-trading": ["trading"],
    "alpha-research": ["trading"],
    "risk-execution": ["trading"],
    "healthtech": ["healthtech"],
    "pos-retail": ["retail"],
    "software-engineer": ["general"],
    "quality-gate": ["general"],
    "documentation-specialist": ["general"],
    "data-architect": ["general"],
}

# Carga siempre estos skills (nunca lazy)
ALWAYS_LOAD_SKILLS: set[str] = {"evolve", "hedgefund"}

# Carga on-demand estos skills cuando el dominio coincide
DOMAIN_TRIGGERED_SKILLS: set[str] = {"quant-trading", "alpha-research", "risk-execution",
                                      "healthtech", "pos-retail"}

# Tokens por nivel
TIER1_TOKENS_PER_SKILL = 50  # name + description
TIER2_TOKENS_PER_SKILL = 500  # minified content
TIER3_TOKENS_PER_SKILL = 2000  # full content
