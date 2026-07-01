"""
Agent Dispatcher — Skill-aware task routing.

Finds relevant procedural skills for a task description and includes them
in the dispatch context if the match is strong enough (>70% similarity).
"""

from __future__ import annotations

import functools
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from harness.evolve_loop.skill_generator import REGISTRY_PATH, SkillGenerator
from harness.memory_rag.lance_vector_store import (
    COLLECTION_PROCEDURAL_SKILLS,
    LanceVectorStore,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIMILARITY_THRESHOLD = 0.70  # 70% match to load skill


# ---------------------------------------------------------------------------
# AgentDispatcher
# ---------------------------------------------------------------------------


class AgentDispatcher:
    """
    Dispatches tasks to agents with optional skill injection.

    If a relevant skill exists (from skills_registry.yaml or LanceDB
    ``procedural_skills``), its .md content is included in the dispatch
    context so the agent can reuse known patterns.
    """

    def __init__(self, vector_store: Optional[LanceVectorStore] = None) -> None:
        """Inicializa la instancia de la clase."""
        self._vector_store = vector_store
        self._stats: Dict[str, Any] = {
            "total_dispatches": 0,
            "skill_matches": 0,
            "no_skill_matches": 0,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_skill_for_task(self, task_description: str) -> Optional[Dict[str, Any]]:
        """
        Find the best-matching skill for a task description.

        Search order:
          1. YAML registry (``skills_registry.yaml``) — keyword match.
          2. LanceDB ``procedural_skills`` — vector similarity.

        Returns:
            The best-matching skill dict with keys (name, path, domain, agent,
            trigger, content, similarity), or ``None``.
        """
        # Lazy import: yaml solo se necesita si hay registro YAML que leer
        import yaml  # noqa: F401

        query_lower = task_description.lower()

        # --- 1. Check YAML registry ---
        registry_match = SkillGenerator.find_in_registry(query_lower)
        if registry_match:
            skill_path = registry_match.get("path", "")
            content = self._read_skill_md(skill_path) if skill_path else ""
            logger.info(
                "Skill found in YAML registry: %s (path=%s)",
                registry_match.get("name"),
                skill_path,
            )
            return {
                **registry_match,
                "content": content,
                "similarity": 0.80,  # YAML keyword match = strong
            }

        # --- 2. Search LanceDB procedural_skills ---
        if self._vector_store is not None:
            lancedb_match = self._search_lancedb_skills(query_lower)
            if lancedb_match and lancedb_match.get("similarity", 0) >= SIMILARITY_THRESHOLD:
                return lancedb_match

        logger.debug("No skill found for: %s", task_description[:80])
        return None

    def dispatch(self, agent_role: str, task_description: str) -> Dict[str, Any]:
        """
        Dispatch a task to an agent, optionally including skill context.

        Args:
            agent_role: The target agent (e.g. "software-engineer").
            task_description: What needs to be done.

        Returns:
            Dict with:
              - ``agent``: The target agent role.
              - ``task``: The task description.
              - ``used_skill``: Whether a skill was injected.
              - ``skill_context``: The skill .md content (or empty str).
              - ``reasoning_mode``: "from_scratch" or "guided_by_skill".
        """
        self._stats["total_dispatches"] += 1

        skill = self.find_skill_for_task(task_description)

        result: Dict[str, Any] = {
            "agent": agent_role,
            "task": task_description,
            "used_skill": False,
            "skill_context": "",
            "reasoning_mode": "from_scratch",
        }

        if skill is not None and skill.get("similarity", 0) >= SIMILARITY_THRESHOLD:
            result["used_skill"] = True
            result["skill_context"] = skill.get("content", "")
            result["reasoning_mode"] = "guided_by_skill"
            result["skill_name"] = skill.get("name", "")
            self._stats["skill_matches"] += 1
            logger.info(
                "Dispatch @%s guided by skill '%s' (sim=%.2f)",
                agent_role,
                skill.get("name"),
                skill.get("similarity", 0),
            )
        else:
            result["reasoning_mode"] = "from_scratch"
            self._stats["no_skill_matches"] += 1
            logger.info(
                "Dispatch @%s from scratch (no skill match > %.0f%%)",
                agent_role,
                SIMILARITY_THRESHOLD * 100,
            )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search_lancedb_skills(self, query: str) -> Optional[Dict[str, Any]]:
        """Search for skills in LanceDB procedural_skills collection."""
        if self._vector_store is None:
            return None

        # Build embedding for query
        dim = 384
        vec = np.zeros(dim, dtype=np.float32)
        for i, ch in enumerate(query.encode("utf-8", errors="replace")):
            idx = (i * 7 + ch) % dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        try:
            results = self._vector_store.search(
                COLLECTION_PROCEDURAL_SKILLS, vec, top_k=3
            )
        except Exception as exc:
            logger.warning("LanceDB skill search failed: %s", exc)
            return None

        if not results:
            return None

        # Take best result with metadata
        best = results[0]
        meta = best.get("metadata", {})
        score = best.get("score", 0.0)

        if score < SIMILARITY_THRESHOLD:
            return None

        skill_name = meta.get("name", "")
        skill_path = str(
            Path(str(REGISTRY_PATH)).parent / "auto" / f"{skill_name}.md"
        )
        content = self._read_skill_md(skill_path)

        return {
            "name": skill_name,
            "path": skill_path,
            "domain": meta.get("domain", ""),
            "agent": meta.get("agent", ""),
            "trigger": meta.get("trigger", ""),
            "content": content,
            "similarity": score,
        }

    @staticmethod
    @functools.lru_cache(maxsize=64)
    def _read_skill_md(path: str) -> str:
        """
        Read a skill .md file, prefer pre-compiled .min.md version.

        Si existe el archivo .min.md (pre-compilado), lo usa para ahorrar
        tokens (~40-60% menos). Si no, cae en el .md original.
        """
        try:
            p = Path(path)
            # Prefer pre-compiled version (SKILL.min.md)
            min_p = p.with_suffix('.min.md')
            if min_p.exists():
                return min_p.read_text(encoding='utf-8')
            if p.exists():
                return p.read_text(encoding='utf-8')
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return dispatch statistics."""
        return dict(self._stats)

    def reset_stats(self) -> None:
        """Reset dispatch counters."""
        self._stats = {
            "total_dispatches": 0,
            "skill_matches": 0,
            "no_skill_matches": 0,
        }
