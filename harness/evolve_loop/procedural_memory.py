"""
Procedural Memory — Hermes-inspired auto-skill generation.

When a multi-step task succeeds, the system can auto-generate a SKILL.md
file in .opencode/skills/auto/ so the agent doesn't need to re-derive
the steps next time.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AUTO_SKILLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".opencode",
    "skills",
    "auto",
)


@dataclass
class ProceduralSkill:
    name: str
    description: str
    steps: List[str]
    agent: str
    tags: List[str] = field(default_factory=list)
    source_task_id: str = ""
    created_at: str = ""
    version: int = 1

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_markdown(self) -> str:
        lines = [
            f"# {self.name}",
            f"",
            f"**Agent:** @{self.agent}",
            f"**Descripcion:** {self.description}",
            f"**Version:** {self.version}",
            f"**Creado:** {self.created_at}",
            f"**Tags:** {', '.join(self.tags)}",
            f"",
            f"## Pasos",
            f"",
        ]
        for i, step in enumerate(self.steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")
        lines.append("---")
        lines.append("*Generado automaticamente por Procedural Memory*")
        return "\n".join(lines)


class ProceduralMemory:
    """
    Stores and retrieves auto-generated skills.

    When the system successfully completes a multi-step task (>3 tool calls),
    it can register a ProceduralSkill so the agent can reuse the pattern.
    """

    def __init__(self, skills_dir: str = "") -> None:
        self._skills_dir = skills_dir or AUTO_SKILLS_DIR
        os.makedirs(self._skills_dir, exist_ok=True)
        self._skills: Dict[str, ProceduralSkill] = {}
        self._load_skills()

    def _load_skills(self) -> None:
        if not os.path.isdir(self._skills_dir):
            return
        for fname in sorted(os.listdir(self._skills_dir)):
            if fname.endswith(".md"):
                name = fname[:-3]
                path = os.path.join(self._skills_dir, fname)
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                lines = content.split("\n")
                description = ""
                steps = []
                agent = ""
                tags: List[str] = []
                in_steps = False
                for line in lines:
                    if line.startswith("**Agent:** @"):
                        agent = line.split("@")[1].strip()
                    elif line.startswith("**Descripcion:**"):
                        description = line.split("**:", 1)[1].strip() if ":" in line else ""
                    elif line.startswith("**Tags:**"):
                        tags_str = line.split("**:", 1)[1].strip() if ":" in line else ""
                        tags = [t.strip() for t in tags_str.split(",") if t.strip()]
                    elif line.strip().startswith("## Pasos"):
                        in_steps = True
                    elif in_steps and re.match(r"^\d+\.\s", line.strip()):
                        step_text = re.sub(r"^\d+\.\s*", "", line.strip())
                        steps.append(step_text)

                self._skills[name] = ProceduralSkill(
                    name=name,
                    description=description,
                    steps=steps,
                    agent=agent,
                    tags=tags,
                    created_at=self._extract_date(content),
                )

    @staticmethod
    def _extract_date(content: str) -> str:
        m = re.search(r"\*\*Creado:\*\*\s*(\S+)", content)
        return m.group(1) if m else ""

    def register_skill(
        self,
        name: str,
        description: str,
        steps: List[str],
        agent: str,
        tags: Optional[List[str]] = None,
        source_task_id: str = "",
    ) -> ProceduralSkill:
        """
        Register a new procedural skill and persist as .md file.
        """
        safe_name = name.lower().replace(" ", "_").replace("/", "_")
        safe_name = re.sub(r"[^a-z0-9_-]", "", safe_name)  # type: ignore[arg-type]

        skill = ProceduralSkill(
            name=safe_name,
            description=description,
            steps=steps,
            agent=agent,
            tags=tags or [],
            source_task_id=source_task_id,
        )

        # Avoid overwriting
        existing_path = os.path.join(self._skills_dir, f"{safe_name}.md")
        if os.path.exists(existing_path):
            skill.version = self._skills.get(safe_name, skill).version + 1

        filepath = os.path.join(self._skills_dir, f"{safe_name}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(skill.to_markdown())

        self._skills[safe_name] = skill
        logger.info(
            "Procedural skill registered: %s (version %d, %d steps)",
            safe_name, skill.version, len(steps),
        )
        return skill

    def find_skill(self, query: str) -> Optional[ProceduralSkill]:
        """
        Find a skill by exact name or partial match.
        """
        query_lower = query.lower().replace(" ", "_")
        if query_lower in self._skills:
            return self._skills[query_lower]

        for name, skill in self._skills.items():
            if query_lower in name or query_lower in skill.description.lower():
                return skill

        for name, skill in self._skills.items():
            if any(query_lower in t.lower() for t in skill.tags):
                return skill

        return None

    def list_skills(self) -> List[ProceduralSkill]:
        return list(self._skills.values())

    def get_skills_for_agent(self, agent: str) -> List[ProceduralSkill]:
        return [s for s in self._skills.values() if s.agent == agent]

    def should_auto_register(self, tool_call_count: int, success: bool) -> bool:
        """
        Heuristic: register a procedural skill if a task took >3 tool calls
        and succeeded.
        """
        return success and tool_call_count > 3
