"""
Procedural Memory — Hermes-inspired auto-skill generation.

When a multi-step task succeeds, the system can auto-generate a SKILL.md
file in .opencode/skills/auto/ so the agent doesn't need to re-derive
the steps next time.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

AUTO_SKILLS_DIR = str(
    Path(__file__).resolve().parent.parent.parent / ".opencode" / "skills" / "auto"
)


@dataclass
class ProceduralSkill:
    """ProceduralSkill."""
    name: str
    description: str
    steps: list[str]
    agent: str
    tags: list[str] = field(default_factory=list)
    source_task_id: str = ""
    created_at: str = ""
    version: int = 1

    def __post_init__(self):
        """Post init."""
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_markdown(self) -> str:
        """To markdown."""
        lines = [
            f"# {self.name}",
            "",
            f"**Agent:** @{self.agent}",
            f"**Descripcion:** {self.description}",
            f"**Version:** {self.version}",
            f"**Creado:** {self.created_at}",
            f"**Tags:** {', '.join(self.tags)}",
            "",
            "## Pasos",
            "",
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
        """Inicializa la instancia de la clase."""
        self._skills_dir = skills_dir or AUTO_SKILLS_DIR
        Path(self._skills_dir).mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, ProceduralSkill] = {}
        self._load_skills()

    def _load_skills(self) -> None:
        skills_path = Path(self._skills_dir)
        if not skills_path.is_dir():
            return
        for fpath in sorted(skills_path.iterdir()):
            if fpath.suffix == ".md":
                name = fpath.stem
                with open(fpath, encoding="utf-8") as f:
                    content = f.read()
                lines = content.split("\n")
                description = ""
                steps = []
                agent = ""
                tags: list[str] = []
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
        steps: list[str],
        agent: str,
        tags: list[str] | None = None,
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
        existing_path = Path(self._skills_dir) / f"{safe_name}.md"
        if existing_path.exists():
            skill.version = self._skills.get(safe_name, skill).version + 1

        filepath = str(Path(self._skills_dir) / f"{safe_name}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(skill.to_markdown())

        self._skills[safe_name] = skill
        logger.info(
            "Procedural skill registered: %s (version %d, %d steps)",
            safe_name, skill.version, len(steps),
        )
        return skill

    def find_skill(self, query: str) -> ProceduralSkill | None:
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

    def list_skills(self) -> list[ProceduralSkill]:
        """List skills."""
        return list(self._skills.values())

    def get_skills_for_agent(self, agent: str) -> list[ProceduralSkill]:
        """Get skills for agent."""
        return [s for s in self._skills.values() if s.agent == agent]

    def should_auto_register(self, tool_call_count: int, success: bool) -> bool:
        """
        Heuristic: register a procedural skill if a task took >3 tool calls
        and succeeded.
        """
        return success and tool_call_count > 3
