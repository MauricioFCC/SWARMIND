"""
Skill Loader — Carga progresiva de skills en 3 niveles (progressive disclosure).

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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Skill metadata
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Lazy Skill Loader
# ---------------------------------------------------------------------------

class LazySkillLoader:
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


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def create_loader(skills_dir: str = ".opencode/skills") -> LazySkillLoader:
    """Create a pre-configured LazySkillLoader."""
    return LazySkillLoader(skills_dir, auto_discover=True)
