"""
Skill Generator — Hermes-inspired auto-skill creation.

When a multi-step task succeeds with >= 5 tool calls, the SkillGenerator
auto-generates a SKILL.md file in .opencode/skills/auto/ and registers it
in the skills_registry.yaml and LanceDB ``procedural_skills`` collection.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from harness.memory_rag.lance_vector_store import (
    COLLECTION_PROCEDURAL_SKILLS,
    LanceVectorStore,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Swarmind/
HARNESS_ROOT = PROJECT_ROOT / "harness"
WORKSPACE_ROOT = PROJECT_ROOT  # Swarmind/

AUTO_SKILLS_DIR = PROJECT_ROOT / ".opencode" / "skills" / "auto"
REGISTRY_PATH = PROJECT_ROOT / ".opencode" / "skills" / "skills_registry.yaml"


# ---------------------------------------------------------------------------
# SkillGenerator
# ---------------------------------------------------------------------------


class SkillGenerator:
    """
    Generates and registers procedural skills from successful multi-step tasks.

    The heuristic:
      - If ``tool_call_count >= 5`` and ``success == True``:
        1. Generate a .md skill file in ``.opencode/skills/auto/<slug>.md``
        2. Register it in ``skills_registry.yaml``
        3. Index it in LanceDB collection ``procedural_skills``
    """

    def __init__(self, vector_store: Optional[LanceVectorStore] = None) -> None:
        """Inicializa la instancia de la clase."""
        self._vector_store = vector_store
        os.makedirs(str(AUTO_SKILLS_DIR), exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_skill(
        self,
        agent: str,
        task_description: str,
        tool_call_count: int,
        success: bool,
        steps: List[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a skill if the heuristic is met.

        Args:
            agent: The agent role that performed the task (e.g. "software-engineer").
            task_description: Natural language description of what was done.
            tool_call_count: Number of tool calls made during the task.
            success: Whether the task completed successfully.
            steps: Ordered list of step descriptions.

        Returns:
            A dict with skill metadata if a skill was generated, or ``None``.
        """
        if not (tool_call_count >= 5 and success):
            logger.debug(
                "Skill not generated: tool_calls=%d success=%s (need >=5 and True)",
                tool_call_count,
                success,
            )
            return None

        if not steps:
            logger.warning("Skill not generated: no steps provided.")
            return None

        # --- Infer domain from agent ---
        domain = self._infer_domain(agent)

        # --- Generate slug ---
        slug = self._make_slug(task_description, agent)

        # --- 1. Write .md file ---
        md_path = AUTO_SKILLS_DIR / f"{slug}.md"
        md_content = self._build_md_content(slug, domain, agent, task_description, steps)
        with open(str(md_path), "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info("Skill .md written: %s", md_path)

        # --- 2. Register in YAML registry ---
        registry_entry = self._register_in_yaml(slug, str(md_path), domain, agent, task_description)

        # --- 3. Index in LanceDB ---
        if self._vector_store is not None:
            self._index_in_lancedb(slug, domain, agent, task_description, steps)

        logger.info(
            "Skill generated: slug=%s domain=%s agent=@%s steps=%d",
            slug,
            domain,
            agent,
            len(steps),
        )
        return registry_entry

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_domain(agent: str) -> str:
        """Map agent role to a domain string."""
        domain_map: Dict[str, str] = {
            "software-engineer": "full-stack-development",
            "data-architect": "data-modeling",
            "devops-sre": "infrastructure-operations",
            "security-engineer": "security-compliance",
            "frontend-engineer": "frontend-ui",
            "mobile-engineer": "mobile-development",
            "ai-engineer": "artificial-intelligence",
            "quant-developer": "quantitative-trading",
            "quant-scientist": "quantitative-research",
            "risk-manager": "risk-management",
            "trading-operations": "trading-operations",
            "project-manager": "project-management",
            "context-engineer": "context-engineering",
            "tool-mcp-engineer": "tool-engineering",
            "quality-gate": "quality-assurance",
            "documentation-specialist": "technical-writing",
            "requirements-analyst": "requirements-analysis",
            "enterprise-architect": "enterprise-architecture",
            "evolve": "self-improvement",
        }
        return domain_map.get(agent, "general")

    @staticmethod
    def _make_slug(task_description: str, agent: str) -> str:
        """Create a URL-safe slug from the task description."""
        # Take first ~5 meaningful words
        words = re.findall(r"[a-zA-Z0-9]+", task_description.lower())
        meaningful = [w for w in words if len(w) > 2][:5]
        if not meaningful:
            meaningful = ["skill", agent.replace("-", "_")]
        base = "_".join(meaningful)
        short_id = uuid.uuid4().hex[:6]
        return f"{base}_{short_id}"

    @staticmethod
    def _build_md_content(
        slug: str, domain: str, agent: str, task_description: str, steps: List[str]
    ) -> str:
        """Build the Markdown content for the skill file."""
        lines = [
            f"# skill: {slug}",
            "",
            f"**Dominio**: {domain}",
            f"**Generado por**: @{agent}",
            f"**Trigger**: {task_description}",
            "**Pasos**:",
        ]
        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")
        lines.append("---")
        lines.append(f"*Generado automaticamente por SkillGenerator en {datetime.now(timezone.utc).isoformat()}*")
        return "\n".join(lines)

    def _register_in_yaml(
        self, slug: str, md_path: str, domain: str, agent: str, trigger: str
    ) -> Dict[str, Any]:
        """Register the skill in skills_registry.yaml."""
        entry: Dict[str, Any] = {
            "name": slug,
            "path": str(md_path),
            "domain": domain,
            "agent": agent,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "trigger": trigger[:200],  # cap length
        }

        registry: Dict[str, List[Dict[str, Any]]] = {"skills": []}
        if REGISTRY_PATH.exists():
            try:
                with open(str(REGISTRY_PATH), "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
                registry = loaded if isinstance(loaded, dict) else {"skills": []}
            except Exception:
                registry = {"skills": []}

        if "skills" not in registry:
            registry["skills"] = []

        # Avoid duplicates by name
        registry["skills"] = [s for s in registry["skills"] if s.get("name") != slug]
        registry["skills"].append(entry)

        with open(str(REGISTRY_PATH), "w", encoding="utf-8") as f:
            yaml.dump(registry, f, default_flow_style=False, allow_unicode=True)

        logger.info("Skill registered in YAML registry: %s", slug)
        return entry

    def _index_in_lancedb(
        self,
        slug: str,
        domain: str,
        agent: str,
        trigger: str,
        steps: List[str],
    ) -> None:
        """Index the skill metadata in LanceDB procedural_skills collection."""
        if self._vector_store is None:
            logger.warning("No vector store available; skipping LanceDB index.")
            return

        import numpy as np

        steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
        now = datetime.now(timezone.utc).isoformat()

        metadata: Dict[str, Any] = {
            "name": slug,
            "domain": domain,
            "agent": agent,
            "trigger": trigger[:200],
            "steps_text": steps_text,
            "created_at": now,
        }

        # Build a simple embedding vector from the text
        text_for_vec = f"{slug} {domain} {trigger} {steps_text}"
        _dim = 384
        vec = np.zeros(_dim, dtype=np.float32)
        for i, ch in enumerate(text_for_vec.encode("utf-8", errors="replace")):
            idx = (i * 7 + ch) % _dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        try:
            self._vector_store.insert(
                COLLECTION_PROCEDURAL_SKILLS,
                vec.reshape(1, -1),
                [metadata],
            )
            logger.info("Skill indexed in LanceDB collection '%s': %s", COLLECTION_PROCEDURAL_SKILLS, slug)
        except Exception as exc:
            logger.warning("Failed to index skill in LanceDB: %s", exc)

    # ------------------------------------------------------------------
    # Utility: find skills in registry
    # ------------------------------------------------------------------

    @staticmethod
    def find_in_registry(query: str) -> Optional[Dict[str, Any]]:
        """Search the YAML registry for a skill matching *query*."""
        if not REGISTRY_PATH.exists():
            return None

        try:
            with open(str(REGISTRY_PATH), "r", encoding="utf-8") as f:
                registry = yaml.safe_load(f) or {}
        except Exception:
            return None

        skills: List[Dict[str, Any]] = registry.get("skills", [])
        query_lower = query.lower()

        best: Optional[Dict[str, Any]] = None
        best_score = 0.0

        for skill in skills:
            name = skill.get("name", "").lower()
            trigger = skill.get("trigger", "").lower()
            domain = skill.get("domain", "").lower()

            score = 0.0
            if query_lower in name:
                score = 1.0
            elif query_lower in trigger:
                score = 0.8
            elif query_lower in domain:
                score = 0.5

            if score > best_score:
                best_score = score
                best = skill

        if best_score >= 0.7:
            return best
        return None
