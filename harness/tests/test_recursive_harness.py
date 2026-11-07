"""Tests de RecursiveHarness (integración de Harness2 en el evolve loop)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from harness.evolve_loop import recursive_harness as rh_module
from harness.evolve_loop.recursive_harness import RecursiveHarness
from harness.harness2 import HarnessTree


def _proposer_fn(_task: str, _harness: Any, _job: str) -> str:
    """Proposer trivial (la recursión está parcheada en estos tests)."""
    return "propuesta"


def _executor(_task: str, _harness: Any) -> Any:
    """Ejecutor trivial."""
    return None


class TestDispatchModos:
    """`run` despacha a sequential/parallel según el argumento `mode`."""

    def _harness(self, monkeypatch, tmp_path) -> tuple[RecursiveHarness, dict]:
        llamadas: dict[str, Any] = {}

        def fake_sequential(**kwargs: Any) -> SimpleNamespace:
            llamadas["modo"] = "sequential"
            llamadas.update(kwargs)
            return SimpleNamespace(modo="sequential")

        def fake_parallel(**kwargs: Any) -> SimpleNamespace:
            llamadas["modo"] = "parallel"
            llamadas.update(kwargs)
            return SimpleNamespace(modo="parallel")

        monkeypatch.setattr(rh_module, "sequential_recursion", fake_sequential)
        monkeypatch.setattr(rh_module, "parallel_recursion", fake_parallel)
        return RecursiveHarness(tmp_path, _proposer_fn), llamadas

    def test_sequential_mode_dispatch(self, monkeypatch, tmp_path):
        """`mode="sequential"` ejecuta sequential_recursion con los kwargs."""
        recursivo, llamadas = self._harness(monkeypatch, tmp_path)
        resultado = recursivo.run(
            "task-1", HarnessTree(), _executor, mode="sequential", k=3, job="mejorar"
        )
        assert resultado.modo == "sequential"
        assert llamadas["modo"] == "sequential"
        assert llamadas["task_id"] == "task-1"
        assert llamadas["k"] == 3
        assert llamadas["job"] == "mejorar"
        assert llamadas["base_harness"].__class__ is HarnessTree
        assert llamadas["executor"] is _executor

    def test_parallel_es_el_default(self, monkeypatch, tmp_path):
        """Sin `mode` se usa parallel_recursion."""
        recursivo, llamadas = self._harness(monkeypatch, tmp_path)
        resultado = recursivo.run("task-2", HarnessTree(), _executor)
        assert resultado.modo == "parallel"
        assert llamadas["modo"] == "parallel"
        assert llamadas["k"] == 1

    def test_recibe_proposer_e_improvement(self, monkeypatch, tmp_path):
        """La recursión recibe el proposer y el improvement del wrapper."""
        recursivo, llamadas = self._harness(monkeypatch, tmp_path)
        recursivo.run("task-3", HarnessTree(), _executor, mode="sequential")
        assert llamadas["proposer"] is recursivo.proposer
        assert llamadas["improvement"] is recursivo.improvement


class TestRunBounded:
    """`run_bounded` aplica presupuesto y score por defecto."""

    def test_score_fn_propio_y_claves_de_resultado(self, tmp_path):
        """El score_fn del caller se usa y el resultado expone las claves."""
        vistas: list[int] = []

        def score_fn(depth: int, _state: Any) -> float:
            vistas.append(depth)
            return 0.5

        recursivo = RecursiveHarness(tmp_path, _proposer_fn)
        resultado = recursivo.run_bounded(
            "task-b", HarnessTree(), _executor, score_fn=score_fn, max_depth=3
        )
        assert vistas, "el score_fn del caller debe ejecutarse"
        assert {"best_score", "best_depth", "history", "stopped_reason"} <= set(resultado)
        assert resultado["best_score"] == pytest.approx(0.5)

    def test_max_depth_acota_la_recursion(self, tmp_path):
        """Con max_depth=1 solo se evalua una iteración."""
        recursivo = RecursiveHarness(tmp_path, _proposer_fn)
        resultado = recursivo.run_bounded(
            "task-d",
            HarnessTree(),
            _executor,
            score_fn=lambda _d, _s: 0.1,
            max_depth=1,
        )
        assert len(resultado["history"]) == 1
        assert resultado["best_depth"] == 0

    def test_score_por_defecto_usa_el_executor(self, tmp_path):
        """Sin score_fn, el executor decide (success -> 1.0)."""
        recursivo = RecursiveHarness(tmp_path, _proposer_fn)
        ok = recursivo.run_bounded(
            "task-ok",
            HarnessTree(),
            lambda _t, _h: SimpleNamespace(success=True),
            max_depth=2,
        )
        assert ok["best_score"] == pytest.approx(1.0)

        fallo = recursivo.run_bounded(
            "task-fail",
            HarnessTree(),
            lambda _t, _h: SimpleNamespace(success=False),
            max_depth=2,
        )
        assert fallo["best_score"] == pytest.approx(0.0)

    def test_executor_que_lanza_no_propaga(self, tmp_path):
        """Una excepción del executor se convierte en score 0 (no propaga)."""
        recursivo = RecursiveHarness(tmp_path, _proposer_fn)
        resultado = recursivo.run_bounded(
            "task-boom",
            HarnessTree(),
            lambda _t, _h: (_ for _ in ()).throw(RuntimeError("boom")),
            max_depth=2,
        )
        assert resultado["best_score"] == pytest.approx(0.0)


class TestAdoptYGuidance:
    """`adopt` delega en ImprovementHarness y `guidance` lo expone."""

    def test_adopt_y_guidance(self, tmp_path):
        recursivo = RecursiveHarness(tmp_path, _proposer_fn)
        tree = HarnessTree()
        recursivo.adopt("h-1", tree, lesson="usar ratchet")
        guidance = recursivo.guidance()
        assert isinstance(guidance, str)
