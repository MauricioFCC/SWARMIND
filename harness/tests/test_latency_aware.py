"""Tests para CriticalPath — LAMaS-lite (ADR-0034, Idea 5).

Cubre: longest path, critical path correcto, optimize preserva topología,
parallel pairs y manejo de planes vacíos.
"""

import pytest

from harness.orchestrator.latency_aware import CriticalPath
from harness.orchestrator.task_planner import SubTask


def _st(stid, deps=None, latency=None):
    """Helper para construir SubTask."""
    return SubTask(
        id=stid,
        agent="builder",
        description=f"subtask {stid}",
        dependencies=list(deps or []),
        estimated_latency_ms=latency,
    )


class TestLongestPath:
    """Cálculo del camino más largo del DAG."""

    def test_linear_chain(self):
        a, b, c = _st("a"), _st("b", ["a"]), _st("c", ["b"])
        cp = CriticalPath()
        path, length = cp.longest_path([a, b, c])
        assert path == ["a", "b", "c"]
        assert length == 3.0

    def test_diamond_picks_longest_branch(self):
        a = _st("a")
        b = _st("b", ["a"])
        c = _st("c", ["a"])
        d = _st("d", ["b", "c"])
        cp = CriticalPath()
        path, length = cp.longest_path([a, b, c, d])
        # Camino a->b->d (o a->c->d) = 3 nodos.
        assert length == 3.0
        assert path[0] == "a"
        assert path[-1] == "d"

    def test_weighted_latency(self):
        a = _st("a")
        b = _st("b", ["a"], latency=100.0)
        c = _st("c", ["a"], latency=300.0)
        cp = CriticalPath()
        path, length = cp.longest_path([a, b, c])
        # a(1.0 default) + c(300) = 301 > a + b(100) = 101
        assert path == ["a", "c"]
        assert length == pytest.approx(301.0)

    def test_empty_plan(self):
        cp = CriticalPath()
        path, length = cp.longest_path([])
        assert path == []
        assert length == 0.0

    def test_parallel_roots(self):
        a, b = _st("a"), _st("b")
        cp = CriticalPath()
        path, length = cp.longest_path([a, b])
        assert length == 1.0
        assert len(path) == 1


class TestCompute:
    """API compute() -> dict con ruta crítica."""

    def test_compute_returns_structure(self):
        a, b = _st("a"), _st("b", ["a"])
        cp = CriticalPath()
        result = cp.compute([a, b])
        assert result["critical_path"] == ["a", "b"]
        assert result["estimated_latency_ms"] == pytest.approx(2.0)
        assert "critical_ids" in result


class TestOptimize:
    """Reordenamiento priorizando ruta crítica (sin romper topología)."""

    def test_optimize_preserves_dependencies(self):
        a = _st("a")
        b = _st("b", ["a"])
        c = _st("c", ["a"])
        d = _st("d", ["b", "c"])
        cp = CriticalPath()
        ordered = cp.optimize([a, b, c, d])
        ids = [s.id for s in ordered]
        # 'a' primero siempre (raíz); 'b','c' después de 'a'; 'd' último.
        assert ids.index("a") < ids.index("b")
        assert ids.index("a") < ids.index("c")
        assert ids.index("b") < ids.index("d")
        assert ids.index("c") < ids.index("d")

    def test_optimize_returns_same_subtasks(self):
        subs = [_st("a"), _st("b", ["a"]), _st("c")]
        cp = CriticalPath()
        ordered = cp.optimize(subs)
        assert {s.id for s in ordered} == {"a", "b", "c"}

    def test_optimize_empty(self):
        cp = CriticalPath()
        assert cp.optimize([]) == []

    def test_optimize_prioritizes_critical(self):
        # Cadena crítica larga (a->b->c) vs paralelo corto (x->y)
        a = _st("a")
        b = _st("b", ["a"])
        c = _st("c", ["b"])
        x = _st("x")
        y = _st("y", ["x"])
        cp = CriticalPath()
        ordered = cp.optimize([x, y, a, b, c])
        ids = [s.id for s in ordered]
        # a (inicio de la ruta crítica) debe estar antes que x
        assert ids.index("a") < ids.index("x")


class TestParallelPairs:
    """Pares de subtasks independientes ejecutables en paralelo."""

    def test_parallel_pairs(self):
        a, b, c = _st("a"), _st("b"), _st("c")
        cp = CriticalPath()
        pairs = cp.parallelizable_pairs([a, b, c])
        assert ("a", "b") in pairs
        assert ("a", "c") in pairs
        assert ("b", "c") in pairs

    def test_no_pairs_in_chain(self):
        a, b, c = _st("a"), _st("b", ["a"]), _st("c", ["b"])
        cp = CriticalPath()
        assert cp.parallelizable_pairs([a, b, c]) == []

    def test_empty(self):
        cp = CriticalPath()
        assert cp.parallelizable_pairs([]) == []
