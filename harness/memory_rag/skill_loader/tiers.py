"""Mixin de carga por niveles (tiers) para ``LazySkillLoader``.

Extraido mecanicamente de ``skill_loader.py`` (regla AGR < 500 lineas).
Contiene los metodos de carga Tier 1/2/3 (progressive disclosure) como
mixin para que ``LazySkillLoader`` (en ``core.py``) conserve la misma
API publica y privada sin cambios de logica ni de firmas.
"""
from __future__ import annotations

import logging

from .constants import (
    ALWAYS_LOAD_SKILLS,
    DOMAIN_TRIGGERED_SKILLS,
    TIER2_TOKENS_PER_SKILL,
    TIER3_TOKENS_PER_SKILL,
)

logger = logging.getLogger("harness.memory_rag.skill_loader")


class _TierMixin:
    """Metodos de carga por tiers para ``LazySkillLoader``."""

    # ------------------------------------------------------------------
    # Tier 1: Always in prompt (name + description only)
    # ------------------------------------------------------------------

    def get_tier1_prompt(
        self,
        domain_filter: list[str] | None = None,
    ) -> str:
        """
        Build Tier 1 prompt section: names + descriptions only.
        This is ALWAYS included in the system prompt.

        Args:
            domain_filter: Optional list of domains to include.
                          If None, all skills are listed.
                          If ["trading"], only trading skills shown.

        Returns:
            String with skill list (~50 tokens per skill).
        """
        lines = ["## Available Skills"]
        lines.append("")
        lines.append("Skills are loaded on-demand. Only load what you need.")
        lines.append("")

        included = 0
        for name, skill in sorted(self._skills.items()):
            # Domain filter
            if domain_filter and not any(d in domain_filter for d in skill.domain):
                continue

            # Don't show domain-triggered skills if not in relevant domain
            if domain_filter is None and name in DOMAIN_TRIGGERED_SKILLS:
                # Still show but mark as lazy
                lines.append(f"- **{name}**: {skill.description[:150]} [lazy]")
            else:
                lines.append(f"- **{name}**: {skill.description[:200]}")
            included += 1

        lines.append("")
        if included > 0:
            lines.append("To load a skill: `/load <skill_name>` or use it naturally.")

        result = "\n".join(lines)
        self._stats["tier1_tokens"] = len(result) // 4
        return result

    # ------------------------------------------------------------------
    # Tier 2: On-demand (minified content)
    # ------------------------------------------------------------------

    def load_tier2(
        self,
        skill_names: list[str],
        force: bool = False,
    ) -> dict[str, bool]:
        """
        Load skills at Tier 2 (minified content).
        Skills are moved from the general pool to 'active'.

        Args:
            skill_names: List of skill names to load.
            force: If True, load even if already loaded.

        Returns:
            {skill_name: success}
        """
        results: dict[str, bool] = {}

        for name in skill_names:
            if name not in self._skills:
                results[name] = False
                continue

            skill = self._skills[name]

            # Already loaded at tier 2 or higher
            if skill.tier >= 2 and not force:
                results[name] = True
                continue

            # Load tier 2 content
            if skill.content_tier2:
                skill.tier = 2
                skill.tokens = TIER2_TOKENS_PER_SKILL
                skill.loaded = True
                self._active_skills[name] = skill
                self._stats["loads_tier2"] += 1
                results[name] = True
                logger.debug("LazySkillLoader: loaded '%s' at tier 2", name)
            else:
                # No minified content, try tier 3
                if skill.content_tier3:
                    self.load_tier3([name])
                    results[name] = True
                else:
                    results[name] = False

        return results

    def load_tier3(
        self,
        skill_names: list[str],
    ) -> dict[str, bool]:
        """
        Load skills at Tier 3 (full content).
        For complex tasks that need the complete skill definition.
        """
        results: dict[str, bool] = {}

        for name in skill_names:
            if name not in self._skills:
                results[name] = False
                continue

            skill = self._skills[name]

            if skill.content_tier3:
                skill.tier = 3
                skill.tokens = TIER3_TOKENS_PER_SKILL
                skill.loaded = True
                self._active_skills[name] = skill
                self._stats["loads_tier3"] += 1
                results[name] = True
                logger.debug("LazySkillLoader: loaded '%s' at tier 3", name)
            else:
                results[name] = False

        return results

    def load_for_domain(
        self,
        domains: list[str],
        tier: int = 2,
    ) -> dict[str, int]:
        """
        Load all skills relevant to given domains.

        Args:
            domains: List of domain names (e.g. ["trading", "general"]).
            tier: Target tier (2 or 3).

        Returns:
            {skill_name: tier_loaded}
        """
        results: dict[str, int] = {}
        to_load: list[str] = []

        for name, skill in self._skills.items():
            # Always-loaded skills
            if name in ALWAYS_LOAD_SKILLS:
                if skill.tier < 2:
                    to_load.append(name)
                continue

            # Domain-triggered skills
            for domain in domains:
                if domain in skill.domain and name in DOMAIN_TRIGGERED_SKILLS:
                    if skill.tier < tier:
                        to_load.append(name)
                    break

        if tier == 2:
            loaded = self.load_tier2(to_load)
        else:
            loaded = self.load_tier3(to_load)

        for name, success in loaded.items():
            if success:
                results[name] = tier

        # Also load always-on skills
        for name in ALWAYS_LOAD_SKILLS:
            s = self._skills.get(name)
            if s and s.tier >= 2:
                results[name] = s.tier

        return results
