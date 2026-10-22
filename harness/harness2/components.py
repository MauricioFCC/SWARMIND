"""Harness2-inspired editable components (8) for recursive harnessing.

Mirrors Google's Harness2: system prompt, guardrails, memory, tool guidance,
subagents, skills, scripts, plugins. These are the editable surfaces of a
harness that task-level recursion (Propose-Probe-Compose) refines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HarnessComponent(str, Enum):
    SYSTEM_PROMPT = "system_prompt"
    GUARDRAILS = "guardrails"
    MEMORY = "memory"
    TOOL_GUIDANCE = "tool_guidance"
    SUBAGENTS = "subagents"
    SKILLS = "skills"
    SCRIPTS = "scripts"
    PLUGINS = "plugins"


@dataclass
class HarnessTree:
    """Editable harness as a dict of components -> payload."""

    components: dict[str, Any] = field(default_factory=dict)

    def get(self, component: str, default: Any = None) -> Any:
        return self.components.get(component, default)

    def set(self, component: str, value: Any) -> None:
        self.components[component] = value

    def to_dict(self) -> dict[str, Any]:
        return dict(self.components)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> HarnessTree:
        return cls(components=dict(data or {}))

    def copy(self) -> HarnessTree:
        import copy
        return HarnessTree(components=copy.deepcopy(self.components))


def diff_summary(base: HarnessTree, new: HarnessTree) -> dict[str, list[str]]:
    """Summarize added/removed/modified components between two trees."""
    base_keys = set(base.components)
    new_keys = set(new.components)
    added = sorted(new_keys - base_keys)
    removed = sorted(base_keys - new_keys)
    modified = sorted(
        k for k in (base_keys & new_keys) if base.components.get(k) != new.components.get(k)
    )
    return {"added": added, "removed": removed, "modified": modified}


def autotrigger(tree: HarnessTree) -> list[str]:
    """Return names of skills/components auto-triggered by the tree (placeholder)."""
    skills = tree.get(HarnessComponent.SKILLS.value, [])
    triggered: list[str] = []
    if isinstance(skills, list):
        for s in skills:
            if isinstance(s, str) and s.startswith("auto:"):
                triggered.append(s)
    return triggered
