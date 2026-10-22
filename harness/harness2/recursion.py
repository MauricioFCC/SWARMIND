"""Parallel and sequential task-level recursion (Harness2-inspired)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .components import HarnessTree, diff_summary
from .context import build, mission
from .probe import probe
from .proposer import Proposer, ProposerError
from .spec import RunView


@dataclass
class Stage:
    label: str
    dim: str
    harness: HarnessTree
    kept_base: bool = False
    fell_back: bool = False
    error: str = ""
    attempts: int = 0
    notes: str = ""


@dataclass
class ModeResult:
    mode: str
    task_id: str
    k: int
    stages: list[Stage] = field(default_factory=list)
    rollouts: dict[str, RunView] = field(default_factory=dict)
    finals: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.finals) and not self.errors


STAGE_ATTEMPTS = 2


def _accept(base: HarnessTree, new: HarnessTree) -> tuple[bool, str]:
    changed = diff_summary(base, new)
    kept = not (changed["added"] or changed["removed"] or changed["modified"])
    return kept, ""


def _run_stage(
    *,
    label: str,
    dim: str,
    job: str,
    fallback: HarnessTree,
    proposer: Proposer,
    ctx_dir_base: str,
    task_id: str,
    rollouts: Sequence[RunView],
    executor: Callable[[str, Any], Any],
    improvement: Any = None,
) -> Stage:
    from pathlib import Path

    try:
        tree = build(Path(ctx_dir_base) / label, task_id, rollouts)
        if improvement is not None:
            g = improvement.guidance()
            if g:
                tree.set("system_prompt", tree.get("system_prompt", "") + "\n\n" + g)
        miss = mission(tree, job=job)
    except Exception as exc:  # noqa: BLE001
        return Stage(label=label, dim=dim, harness=fallback.copy(), fell_back=True, error=f"build evidence: {exc}")

    err = ""
    new_tree = fallback.copy()
    attempts = 0
    for attempt in range(1, STAGE_ATTEMPTS + 1):
        attempts = attempt
        try:
            proposed = proposer.call(miss, fallback.to_dict(), f"{label}.a{attempt}")
            if isinstance(proposed, HarnessTree):
                new_tree = proposed
            elif isinstance(proposed, dict):
                new_tree = HarnessTree.from_dict(proposed)
            else:
                new_tree = HarnessTree.from_dict(dict(proposed))
            kept, verr = _accept(fallback, new_tree)
            if verr:
                err = verr
                continue
            # probe
            rv = probe(executor, task_id, new_tree and label, new_tree)
            if rv.success:
                return Stage(label=label, dim=dim, harness=new_tree, kept_base=kept, attempts=attempts)
            err = f"probe failed: {rv.notes}"
        except ProposerError as exc:
            err = str(exc)
            break
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            break
    # fallback
    return Stage(label=label, dim=dim, harness=fallback.copy(), fell_back=True, error=err, attempts=attempts)


def parallel_recursion(
    *,
    task_id: str,
    k: int,
    base_harness: HarnessTree,
    proposer: Proposer,
    executor: Callable[[str, Any], Any],
    job: str = "improve harness",
    improvement: Any = None,
) -> ModeResult:
    """Parallel recursion: probe k general + k domain candidates, compose k."""
    result = ModeResult(mode="parallel", task_id=task_id, k=k)
    # base execution
    base_rv = probe(executor, task_id, "base", base_harness)
    result.rollouts["base"] = base_rv
    rollouts = [base_rv]
    stages: list[Stage] = []
    # k general candidates
    labels = [f"g{i}" for i in range(k)] + [f"d{i}" for i in range(k)]
    with ThreadPoolExecutor(max_workers=max(1, min(len(labels), 8))) as pool:
        futs = {
            pool.submit(
                _run_stage,
                label=lbl,
                dim="general" if lbl.startswith("g") else "domain",
                job=job,
                fallback=base_harness,
                proposer=proposer,
                ctx_dir_base="ctx",
                task_id=task_id,
                rollouts=rollouts,
                executor=executor,
                improvement=improvement,
            ): lbl
            for lbl in labels
        }
        for fut in futs:
            st = fut.result()
            stages.append(st)
            result.rollouts[st.label] = probe(executor, task_id, st.label, st.harness)
    result.stages = stages
    # compose: pick best successful stage
    successful = [s for s in stages if not s.fell_back]
    if successful:
        best = successful[0]
        result.finals = [best.label]
    else:
        result.finals = ["base"]
        result.errors.append("all stages fell back")
    return result


def sequential_recursion(
    *,
    task_id: str,
    k: int,
    base_harness: HarnessTree,
    proposer: Proposer,
    executor: Callable[[str, Any], Any],
    job: str = "improve harness",
    improvement: Any = None,
) -> ModeResult:
    """Sequential recursion: refine through k successive PPC steps."""
    result = ModeResult(mode="sequential", task_id=task_id, k=k)
    current = base_harness.copy()
    rollouts: list[RunView] = [probe(executor, task_id, "base", current)]
    result.rollouts["base"] = rollouts[0]
    stages: list[Stage] = []
    for i in range(k):
        label = f"step{i}"
        st = _run_stage(
            label=label,
            dim="sequential",
            job=job,
            fallback=current,
            proposer=proposer,
            ctx_dir_base="ctx",
            task_id=task_id,
            rollouts=rollouts,
            executor=executor,
            improvement=improvement,
        )
        stages.append(st)
        if not st.fell_back:
            current = st.harness.copy()
        rv = probe(executor, task_id, label, current)
        rollouts.append(rv)
        result.rollouts[label] = rv
    result.stages = stages
    if stages and not all(s.fell_back for s in stages):
        result.finals = [stages[-1].label]
    else:
        result.finals = ["base"]
        if all(s.fell_back for s in stages):
            result.errors.append("all steps fell back")
    return result
