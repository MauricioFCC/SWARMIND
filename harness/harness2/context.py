"""Evidence context builder (Harness2-inspired)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .components import HarnessTree
from .spec import RunView


def build(
    ctx_dir: Path,
    task_id: str,
    rollouts: Sequence[RunView],
    *,
    pool: Sequence[tuple[str, Path, RunView | None]] | None = None,
    decisions: dict[str, str] | None = None,
) -> HarnessTree:
    """Build an evidence context tree from rollouts (deterministic)."""
    ctx_dir.mkdir(parents=True, exist_ok=True)
    successes = [r for r in rollouts if r.success]
    failures = [r for r in rollouts if not r.success]
    comp = {
        "system_prompt": f"Task: {task_id}\nEvidence: {len(successes)} successes, {len(failures)} failures.",
        "memory": [r.to_dict() for r in rollouts],
        "tool_guidance": "",
        "skills": [],
        "scripts": [],
        "subagents": [],
        "guardrails": [],
        "plugins": [],
    }
    return HarnessTree(components=comp)


def mission(tree: HarnessTree, *, job: str = "") -> str:
    """Produce a mission string for the proposer from an evidence tree."""
    base = tree.get("system_prompt", "")
    return (f"{base}\n\nJob: {job}").strip()
