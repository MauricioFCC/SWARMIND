"""Modelo de metadatos de skill: ``SkillInfo``.

Extraido mecanicamente de ``skill_loader.py`` (regla AGR < 500 lineas).
Sin cambios de logica ni de firmas.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SkillInfo:
    """Metadata about a loaded skill."""
    name: str
    description: str
    tier: int = 1  # 1 = name+desc only, 2 = minified, 3 = full
    tokens: int = 0
    domain: list[str] = field(default_factory=list)
    content_tier2: str = ""  # SKILL.min.md content
    content_tier3: str = ""  # Full SKILL.md content
    loaded: bool = False
    hit_count: int = 0

    def to_tier1(self) -> str:
        """Tier 1: Solo name + description (~50 tokens)."""
        return f"- **{self.name}**: {self.description[:200]}"

    def to_tier2(self) -> str:
        """Tier 2: Content with progressive disclosure markers."""
        return self.content_tier2 or self.content_tier3

    def to_tier3(self) -> str:
        """Tier 3: Full content."""
        return self.content_tier3
