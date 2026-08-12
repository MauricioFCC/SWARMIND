"""Skill Loader — Carga progresiva de skills en 3 niveles (progressive disclosure).

Este paquete reemplaza al modulo ``skill_loader.py`` (regla AGR: archivo
< 500 lineas). Todos los simbolos publicos del modulo original se
re-exportan desde aqui, por lo que los imports existentes
(``from harness.memory_rag.skill_loader import LazySkillLoader``) siguen
funcionando identicos y los parches de tests que apuntan a
``harness.memory_rag.skill_loader.X`` siguen afectando al paquete.

Basado en el patron "Lazy Skills" y "SkillsInjector" (arXiv:2605.29794, May 2026):
  - Tier 1 (siempre en prompt): solo name + description (~50 tokens por skill)
  - Tier 2 (on-demand): SKILL.min.md completo cuando el skill se activa
  - Tier 3 (full): SKILL.md completo para tareas complejas
  - Context-aware: solo cargar skills relevantes al dominio actual

Ahorro estimado:
  - Sin lazy loading: ~14K tokens siempre en contexto
  - Con lazy loading: ~500 tokens (nombres) + ~2K (skills activos) = ~2.5K tokens (~82% menos)
"""
from __future__ import annotations

import logging

from .constants import (
    ALWAYS_LOAD_SKILLS,
    DOMAIN_KEYWORDS,
    DOMAIN_TRIGGERED_SKILLS,
    SKILL_DOMAIN_MAP,
    TIER1_TOKENS_PER_SKILL,
    TIER2_TOKENS_PER_SKILL,
    TIER3_TOKENS_PER_SKILL,
)
from .core import LazySkillLoader, create_loader
from .models import SkillInfo

logger = logging.getLogger("harness.memory_rag.skill_loader")

__all__ = [
    "ALWAYS_LOAD_SKILLS",
    "DOMAIN_KEYWORDS",
    "DOMAIN_TRIGGERED_SKILLS",
    "SKILL_DOMAIN_MAP",
    "TIER1_TOKENS_PER_SKILL",
    "TIER2_TOKENS_PER_SKILL",
    "TIER3_TOKENS_PER_SKILL",
    "LazySkillLoader",
    "SkillInfo",
    "create_loader",
    "logger",
]
