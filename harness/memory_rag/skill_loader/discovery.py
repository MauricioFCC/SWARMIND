"""Mixin de discovery para ``LazySkillLoader``.

Extraido mecanicamente de ``skill_loader.py`` (regla AGR < 500 lineas).
Contiene el descubrimiento de skills en el directorio y la extraccion de
la description del frontmatter como mixin para que ``LazySkillLoader``
(en ``core.py``) conserve la misma API publica y privada sin cambios de
logica ni de firmas.
"""
from __future__ import annotations

import logging
import re

from .constants import SKILL_DOMAIN_MAP, TIER1_TOKENS_PER_SKILL
from .models import SkillInfo

logger = logging.getLogger("harness.memory_rag.skill_loader")


class _DiscoveryMixin:
    """Metodos de discovery de skills para ``LazySkillLoader``."""

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_skills(self) -> None:
        """Discover all skills in the skills directory."""
        if not self._skills_dir.exists():
            logger.warning("Skills directory not found: %s", self._skills_dir)
            return

        for skill_dir in sorted(self._skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            # Leer SKILL.md o SKILL.min.md
            full_file = skill_dir / "SKILL.md"
            min_file = skill_dir / "SKILL.min.md"

            name = skill_dir.name

            # Extraer description del frontmatter
            description = ""
            if full_file.exists():
                content_full = full_file.read_text(encoding="utf-8")
                description = self._extract_description(content_full)
            elif min_file.exists():
                content_min = min_file.read_text(encoding="utf-8")
                description = self._extract_description(content_min)

            if not description:
                description = f"Skill: {name}"

            # Domain mapping
            domains = SKILL_DOMAIN_MAP.get(name, ["general"])

            skill = SkillInfo(
                name=name,
                description=description,
                tier=1,
                tokens=TIER1_TOKENS_PER_SKILL,
                domain=domains,
            )

            # Cache content for tiers 2 and 3
            if full_file.exists():
                skill.content_tier3 = content_full
            if min_file.exists():
                skill.content_tier2 = min_file.read_text(encoding="utf-8")
            elif full_file.exists():
                # Fallback: use full as tier 2 too
                skill.content_tier2 = content_full

            self._skills[name] = skill

    @staticmethod
    def _extract_description(content: str) -> str:
        """Extract 'description' field from YAML frontmatter."""
        match = re.search(
            r'description:\s*"([^"]*)"',
            content,
        )
        if match:
            return match.group(1)
        match = re.search(
            r"description:\s*'([^']*)'",
            content,
        )
        if match:
            return match.group(1)
        match = re.search(
            r"description:\s*(.+)",
            content,
        )
        if match:
            return match.group(1).strip()
        return ""
