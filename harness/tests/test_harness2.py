"""Tests para harness.harness2 (recursive harnessing inspirado en Google Harness2)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from harness.harness2 import (
    HarnessTree,
    ModeResult,
    Proposer,
    diff_summary,
    validate,
)
from harness.harness2.components import autotrigger
from harness.harness2.context import build, mission
from harness.harness2.improvement_harness import ImprovementHarness
from harness.harness2.library import HarnessLibrary
from harness.harness2.probe import probe
from harness.harness2.recursion import parallel_recursion, sequential_recursion
from harness.harness2.tree import TreeValidationError


def test_harness_tree_diff_and_copy() -> None:
    a = HarnessTree(components={'system_prompt': 'x', 'skills': []})
    b = HarnessTree(components={'system_prompt': 'y', 'skills': [], 'memory': [1]})
    d = diff_summary(a, b)
    assert 'memory' in d['added']
    assert 'system_prompt' in d['modified']
    c = a.copy()
    c.set('system_prompt', 'z')
    assert a.get('system_prompt') == 'x'


def test_validate_rejects_reserved_and_grader() -> None:
    t = HarnessTree(components={'scripts': ['eval'], 'system_prompt': 'ok'})
    with pytest.raises(TreeValidationError):
        validate(t)
    t2 = HarnessTree(components={'system_prompt': 'GRADER_VERDICT: pass'})
    with pytest.raises(TreeValidationError):
        validate(t2)
    validate(HarnessTree(components={'scripts': ['safe']}))


def test_autotrigger() -> None:
    t = HarnessTree(components={'skills': ['auto:x', 'manual']})
    assert autotrigger(t) == ['auto:x']


def test_context_build_and_mission() -> None:
    from harness.harness2.spec import RunView
    rvs = [RunView(run_id='r1', task_id='t', harness_id='h', success=True)]
    tree = build(Path(tempfile.mkdtemp()) / 'ctx', 't', rvs)
    assert 'system_prompt' in tree.components
    m = mission(tree, job='improve')
    assert 'improve' in m


def test_probe() -> None:
    def exec_fn(tid, h):
        return {'success': True, 'output': 'hi', 'metrics': {'s': 1}, 'cost_usd': 0.5}
    rv = probe(exec_fn, 't1', 'h1', {})
    assert rv.success is True
    assert rv.output == 'hi'
    assert rv.cost_usd == 0.5


def test_parallel_and_sequential() -> None:
    base = HarnessTree(components={'system_prompt': 'base'})
    def exec_fn(tid, h):
        return {'success': True, 'output': 'ok'}
    def prop(mission, root, label):
        t = HarnessTree.from_dict(dict(root))
        t.set('system_prompt', t.get('system_prompt', '') + ' [v]')
        return t
    p = Proposer(call_fn=prop)
    pr = parallel_recursion(task_id='t', k=2, base_harness=base, proposer=p, executor=exec_fn)
    assert isinstance(pr, ModeResult)
    assert pr.ok is True
    assert len(pr.stages) == 4
    sr = sequential_recursion(task_id='t', k=2, base_harness=base, proposer=p, executor=exec_fn)
    assert sr.ok is True
    assert len(sr.stages) == 2


def test_improvement_harness_and_library() -> None:
    d = Path(tempfile.mkdtemp())
    ih = ImprovementHarness(d)
    tree = HarnessTree(components={'system_prompt': 'x'})
    ih.update('h1', tree, lesson='l1')
    assert 'l1' in ih.lessons()
    assert ih.guidance() != ''
    lib = HarnessLibrary(d / 'lib2')
    lib.adopt('h2', tree, notes='n2')
    assert 'h2' in lib.list_ids()
    assert lib.get('h2') is not None


def test_proposer_error() -> None:
    def bad(mission, root, label):
        raise RuntimeError('boom')
    p = Proposer(call_fn=bad, max_attempts=2)
    with pytest.raises(Exception):  # noqa: B017
        p.call('m', {}, 'l')


def test_recursive_harness_integration() -> None:
    from harness.evolve_loop.recursive_harness import RecursiveHarness
    base = HarnessTree(components={'system_prompt': 'base'})
    def exec_fn(tid, h):
        return {'success': True, 'output': 'ok'}
    def prop(mission, root, label):
        t = HarnessTree.from_dict(dict(root))
        t.set('system_prompt', t.get('system_prompt', '') + ' [v]')
        return t
    rh = RecursiveHarness(tempfile.mkdtemp(), prop)
    res = rh.run('t', base, exec_fn, mode='parallel', k=1)
    assert res.ok is True
    rh.adopt('adopted', base, lesson='adopted lesson')
    assert 'adopted lesson' in rh.guidance()
