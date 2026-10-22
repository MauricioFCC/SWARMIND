"""Recursive harnessing integration (Harness2-inspired) for SWARMIND evolve loop."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from harness.harness2 import HarnessTree, ImprovementHarness, Proposer
from harness.harness2.recursion import ModeResult, parallel_recursion, sequential_recursion


class RecursiveHarness:
    """Wraps Harness2 recursive harnessing for SWARMIND self-improvement."""

    def __init__(self, base_dir: Path | str, proposer_fn: Callable[[str, Any, str], Any]) -> None:
        self.improvement = ImprovementHarness(base_dir)
        self.proposer = Proposer(call_fn=proposer_fn)

    def run(
        self,
        task_id: str,
        base_harness: HarnessTree,
        executor: Callable[[str, Any], Any],
        *,
        mode: str = "parallel",
        k: int = 1,
        job: str = "improve harness",
    ) -> ModeResult:
        if mode == "sequential":
            return sequential_recursion(
                task_id=task_id,
                k=k,
                base_harness=base_harness,
                proposer=self.proposer,
                executor=executor,
                job=job,
                improvement=self.improvement,
            )
        return parallel_recursion(
            task_id=task_id,
            k=k,
            base_harness=base_harness,
            proposer=self.proposer,
            executor=executor,
            job=job,
            improvement=self.improvement,
        )

    def adopt(self, harness_id: str, tree: HarnessTree, *, lesson: str = "") -> None:
        self.improvement.update(harness_id, tree, lesson=lesson)

    def guidance(self) -> str:
        return self.improvement.guidance()
