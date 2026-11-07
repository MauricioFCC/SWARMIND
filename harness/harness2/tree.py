"""Harness tree validation (Harness2-inspired)."""

from __future__ import annotations

from typing import Any

from .components import HarnessTree

RESERVED_SCRIPTS: frozenset[str] = frozenset({"eval", "grade", "judge"})


class TreeValidationError(ValueError):
    """Raised when a harness tree fails validation."""


def validate(
    tree: HarnessTree | dict[str, Any],
    *,
    allow_subagents: bool = True,
    reserved_scripts: frozenset[str] | None = None,
) -> None:
    """Validate a harness tree.

    - subagents must be allowed if present (unless allow_subagents).
    - scripts must not collide with reserved scripts.
    - tree must be a mapping.
    """
    data = tree.to_dict() if isinstance(tree, HarnessTree) else (tree or {})
    if not isinstance(data, dict):
        raise TreeValidationError("tree must be a mapping")
    reserved = reserved_scripts or RESERVED_SCRIPTS
    scripts = data.get("scripts", [])
    if isinstance(scripts, (list, tuple, set)):
        for s in scripts:
            if str(s) in reserved:
                raise TreeValidationError(f"reserved script name: {s}")
    subagents = data.get("subagents", [])
    if subagents and not allow_subagents:
        raise TreeValidationError("subagents not allowed for this adapter")
    # no grader verdicts in system prompt / tool guidance
    for key in ("system_prompt", "tool_guidance"):
        val = data.get(key)
        if isinstance(val, str) and "GRADER_VERDICT" in val.upper():
            raise TreeValidationError(f"grader verdict leaked into {key}")
