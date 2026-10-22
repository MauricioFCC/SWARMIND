"""Spec / adapter layer (Harness2-inspired)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class RunView:
    """A single execution's observable trace."""

    run_id: str
    task_id: str
    harness_id: str
    output: str = ""
    success: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "harness_id": self.harness_id,
            "output": self.output,
            "success": self.success,
            "metrics": dict(self.metrics),
            "cost_usd": self.cost_usd,
            "notes": self.notes,
        }


class BenchmarkAdapter(Protocol):
    """Adapter for a benchmark/task family."""

    name: str
    allow_subagents: bool
    reserved_scripts: frozenset[str]

    def surface(self) -> Any: ...

    def validate_tree(self, tree: Any) -> None: ...


def resolve_prompts(base: str, overrides: dict[str, str] | None = None) -> str:
    """Resolve a prompt with optional overrides."""
    if not overrides:
        return base
    out = base
    for k, v in overrides.items():
        out = out.replace("{{" + k + "}}", v)
    return out
