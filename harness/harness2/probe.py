"""Probe execution (Harness2-inspired)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .spec import RunView


def probe(
    executor: Callable[[str, Any], Any],
    task_id: str,
    harness_id: str,
    harness: Any,
) -> RunView:
    """Run a harness on a task via an executor and return a RunView.

    executor(task_id, harness) -> dict with keys output/success/metrics/cost_usd.
    """
    try:
        res = executor(task_id, harness) or {}
        return RunView(
            run_id=str(res.get("run_id", f"{task_id}-{harness_id}")),
            task_id=task_id,
            harness_id=harness_id,
            output=str(res.get("output", "")),
            success=bool(res.get("success", False)),
            metrics=dict(res.get("metrics", {}) or {}),
            cost_usd=float(res.get("cost_usd", 0.0) or 0.0),
            notes=str(res.get("notes", "")),
        )
    except Exception as exc:  # noqa: BLE001
        return RunView(
            run_id=f"{task_id}-{harness_id}",
            task_id=task_id,
            harness_id=harness_id,
            output="",
            success=False,
            notes=f"probe error: {exc}",
        )
