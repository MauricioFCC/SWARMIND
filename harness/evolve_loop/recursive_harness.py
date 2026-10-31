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

    def run_bounded(
        self,
        task_id: str,
        base_harness: HarnessTree,
        executor: Callable[[str, Any], Any],
        *,
        score_fn: Callable[[int, Any], float] | None = None,
        max_depth: int | None = None,
        max_tokens: int | None = None,
        timeout_sec: float | None = None,
    ) -> dict[str, Any]:
        """Ejecuta la recursion con limites de recursos (Spec recursive-harness).

        Args:
            task_id: Identificador de la tarea.
            base_harness: Harness base.
            executor: Ejecutor de probes.
            score_fn: Funcion de score (depth, state) -> float.
            max_depth: Profundidad maxima.
            max_tokens: Tokens maximos.
            timeout_sec: Timeout en segundos.

        Returns:
            Resultado de BoundedRecursion.run().
        """
        from .bounded_recursion import BoundedRecursion, RecursionBudget

        budget = RecursionBudget()
        if max_depth is not None:
            budget.max_depth = max_depth
        if max_tokens is not None:
            budget.max_tokens = max_tokens
        if timeout_sec is not None:
            budget.timeout_sec = timeout_sec

        if score_fn is None:
            def score_fn(depth: int, state: Any) -> float:
                try:
                    rv = executor(task_id, base_harness)
                    return 1.0 if getattr(rv, "success", False) else 0.0
                except Exception:  # noqa: BLE001
                    return 0.0

        br = BoundedRecursion(score_fn=score_fn, budget=budget)
        return br.run(initial=base_harness)

    def adopt(self, harness_id: str, tree: HarnessTree, *, lesson: str = "") -> None:
        self.improvement.update(harness_id, tree, lesson=lesson)

    def guidance(self) -> str:
        return self.improvement.guidance()
