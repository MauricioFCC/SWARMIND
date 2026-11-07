"""Tests para BoundedRecursion (Spec recursive-harness-optimization)."""

from __future__ import annotations

from harness.evolve_loop.bounded_recursion import BoundedRecursion, RecursionBudget


def test_bounded_recursion_respects_max_depth():
    calls = []

    def score_fn(depth, state):
        calls.append(depth)
        return float(depth)

    br = BoundedRecursion(score_fn=score_fn, budget=RecursionBudget(max_depth=3, max_tokens=10000, timeout_sec=10))
    res = br.run(initial=None)
    assert res["depth_used"] <= 3
    assert len(res["history"]) <= 3
    assert res["best_depth"] == 2  # scores 0,1,2 -> best at depth 2


def test_bounded_recursion_early_stop():
    # score always 0.5 -> no improvement after first -> early stop after patience
    def score_fn(depth, state):
        return 0.5

    br = BoundedRecursion(score_fn=score_fn, budget=RecursionBudget(max_depth=10, max_tokens=100000, timeout_sec=10), patience=2)
    res = br.run()
    assert res["stopped_reason"] == "early_stop_convergence"
    assert len(res["history"]) <= 3


def test_bounded_recursion_budget_tokens():
    def score_fn(depth, state):
        return 0.1

    br = BoundedRecursion(score_fn=score_fn, budget=RecursionBudget(max_depth=100, max_tokens=150, timeout_sec=10))
    res = br.run()
    assert res["tokens_used"] <= 150 or res["stopped_reason"] in ("budget_exhausted", "early_stop_convergence")


def test_recursion_budget_exhausted():
    b = RecursionBudget(max_depth=2, max_tokens=1000, timeout_sec=10)
    b.record(depth=2)
    assert b.exhausted()


def test_bounded_recursion_handles_error():
    def score_fn(depth, state):
        if depth == 1:
            raise RuntimeError("boom")
        return 0.5

    br = BoundedRecursion(score_fn=score_fn, budget=RecursionBudget(max_depth=5, max_tokens=10000, timeout_sec=10))
    res = br.run()
    assert res["stopped_reason"] == "error"
    assert len(res["history"]) == 1
