"""Clase principal ``LazySkillLoader`` + factory ``create_loader``.

Extraido mecanicamente de ``skill_loader.py`` (regla AGR < 500 lineas).
La clase conserva la misma API publica y privada; el discovery vive en
el mixin de ``discovery.py`` y la carga por tiers en ``tiers.py``. Sin
cambios de logica.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .constants import DOMAIN_KEYWORDS
from .discovery import _DiscoveryMixin
from .models import SkillInfo
from .tiers import _TierMixin

logger = logging.getLogger("harness.memory_rag.skill_loader")


class LazySkillLoader(_DiscoveryMixin, _TierMixin):
    """
    Carga progresiva de skills en 3 niveles.

    Uso:
        loader = LazySkillLoader(".opencode/skills")

        # Tier 1: solo nombres (siempre en prompt)
        tier1 = loader.get_tier1_prompt()  # ~500 tokens para 10 skills

        # Detectar dominio del mensaje
        domains = loader.detect_domains("implement a trading strategy")

        # Tier 2: cargar skills del dominio detectado
        loader.load_tier2(domains)
        context = loader.get_active_skills_context()  # ~2K tokens

        # Tier 3: skill especifico completo
        loader.load_tier3("quant-trading")
    """

    def __init__(
        self,
        skills_dir: str = ".opencode/skills",
        auto_discover: bool = True,
    ) -> None:
        self._skills_dir = Path(skills_dir)
        self._skills: dict[str, SkillInfo] = {}
        self._active_skills: dict[str, SkillInfo] = {}  # tier 2/3 loaded
        self._domain_cache: dict[str, list[str]] = {}
        self._stats: dict[str, Any] = {
            "tier1_tokens": 0,
            "tier2_tokens": 0,
            "tier3_tokens": 0,
            "loads_tier2": 0,
            "loads_tier3": 0,
            "hits": 0,
        }

        if auto_discover:
            self.discover_skills()

        logger.info(
            "LazySkillLoader initialized: %d skills discovered in %s",
            len(self._skills), skills_dir,
        )

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------

    def get_active_skills_context(self) -> str:
        """
        Build the context string for all currently active (loaded) skills.
        Tier 1 skills are listed compactly, tier 2/3 have full content.

        Returns:
            Formatted string for LLM context.
        """
        parts: list[str] = []

        # Loaded skills (tier 2 or 3)
        if self._active_skills:
            parts.append("## Loaded Skills\n")
            for name, skill in sorted(self._active_skills.items()):
                level = "full" if skill.tier == 3 else "minified"
                parts.append(f"### {name} ({level})\n")
                if skill.tier == 3:
                    parts.append(skill.content_tier3)
                else:
                    parts.append(skill.content_tier2)
                parts.append("")

        # Track tokens
        total = sum(len(p) // 4 for p in parts)
        self._stats["tier2_tokens"] = total

        return "\n".join(parts)

    def get_loaded_skill_names(self, tier: int | None = None) -> list[str]:
        """Get names of loaded skills, optionally filtered by tier."""
        if tier:
            return [n for n, s in self._skills.items() if s.tier >= tier]
        return [n for n, s in self._skills.items() if s.loaded]

    # ------------------------------------------------------------------
    # Domain detection
    # ------------------------------------------------------------------

    def detect_domains(self, message: str) -> list[str]:
        """
        Detect which domains are relevant to a message.

        Args:
            message: The user message or task description.

        Returns:
            List of domain names ranked by relevance score.
        """
        if not message:
            return ["general"]

        msg_lower = message.lower()
        scores: dict[str, int] = {}

        for domain, keywords in DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in msg_lower)
            if score > 0:
                scores[domain] = score

        if not scores:
            return ["general"]

        # Sort by score descending
        sorted_domains = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        result = [d for d, _ in sorted_domains]

        # Always include 'general' as fallback
        if "general" not in result:
            result.append("general")

        self._domain_cache[message[:100]] = result
        return result

    # ------------------------------------------------------------------
    # Hit tracking
    # ------------------------------------------------------------------

    def record_hit(self, skill_name: str) -> None:
        """Record that a skill was invoked."""
        skill = self._skills.get(skill_name)
        if skill:
            skill.hit_count += 1
            self._stats["hits"] += 1

            # Auto-promote frequently used skills to tier 2
            if skill.hit_count >= 3 and skill.tier < 2:
                self.load_tier2([skill_name])

    def get_skill(self, name: str) -> SkillInfo | None:
        """Get skill info by name."""
        return self._skills.get(name)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return loader statistics."""
        stats = dict(self._stats)
        stats["total_skills"] = len(self._skills)
        stats["active_skills"] = len(self._active_skills)
        stats["tier1_only"] = sum(1 for s in self._skills.values() if s.tier == 1)
        stats["tier2_loaded"] = sum(1 for s in self._skills.values() if s.tier == 2)
        stats["tier3_loaded"] = sum(1 for s in self._skills.values() if s.tier == 3)
        # Estimate total tokens saved vs loading everything
        all_full_tokens = sum(
            (len(s.content_tier3) // 4) if s.content_tier3 else 0
            for s in self._skills.values()
        )
        current_tokens = stats["tier1_tokens"] + stats["tier2_tokens"] + stats["tier3_tokens"]
        stats["tokens_saved"] = max(0, all_full_tokens - current_tokens)
        stats["tokens_saved_pct"] = round(
            (1 - current_tokens / max(all_full_tokens, 1)) * 100, 1
        ) if all_full_tokens > 0 else 0
        return stats


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def create_loader(skills_dir: str = ".opencode/skills") -> LazySkillLoader:
    """Create a pre-configured LazySkillLoader."""
    return LazySkillLoader(skills_dir, auto_discover=True)
