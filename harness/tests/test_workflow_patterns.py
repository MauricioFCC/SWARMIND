"""Tests para Workflow Patterns — Evaluator-Optimizer, Voting, Critique-Revise, Parallel-Transform."""
from __future__ import annotations
import pytest
from harness.orchestrator.workflow_patterns import (
    evaluator_optimizer, voting, critique_revise, parallel_transform,
    PatternResult,
)


def _gen_ok(task: str) -> str:
    return f"solucion para: {task}"


def _gen_better(task: str) -> str:
    return f"solucion MEJORADA para: {task}"


def _evaluator(task: str, result: str) -> float:
    if "MEJORADA" in result:
        return 0.95
    if "solucion" in result:
        return 0.6
    return 0.0


def _critic(task: str, result: str) -> str:
    if "mejorar" in result.lower():
        return ""
    if "TODO" in result:
        return "Falta implementar validacion"
    return "Falta documentacion"


def _merge(results):
    return "\n---\n".join(results)


class TestEvaluatorOptimizer:
    def test_acepta_en_primer_intento(self):
        """Si el score supera threshold, acepta en iter 1."""
        result = evaluator_optimizer(
            generator_fn=_gen_better,
            evaluator_fn=_evaluator,
            task="test",
            max_iterations=3,
            quality_threshold=0.8,
        )
        assert result.success is True
        assert result.iterations == 1
        assert "MEJORADA" in result.output

    def test_loop_hasta_max_iterations(self):
        """Si no alcanza threshold, itera hasta max_iterations."""
        result = evaluator_optimizer(
            generator_fn=_gen_ok,
            evaluator_fn=_evaluator,
            task="test",
            max_iterations=3,
            quality_threshold=0.99,
        )
        assert result.success is False
        assert result.iterations == 3
        assert len(result.scores) == 3

    def test_traces_registradas(self):
        """Cada iteracion genera un trace."""
        result = evaluator_optimizer(
            generator_fn=_gen_ok,
            evaluator_fn=_evaluator,
            task="test",
            max_iterations=2,
            quality_threshold=0.99,
        )
        assert len(result.traces) == 2
        assert all("iteration" in t for t in result.traces)
        assert all("score" in t for t in result.traces)


class TestVoting:
    def test_elige_mejor_candidato(self):
        """Voting debe seleccionar el candidato con mayor score."""
        results = voting(
            generator_fns=[_gen_ok, _gen_better],
            evaluator_fn=_evaluator,
            task="test",
        )
        assert results.success is True
        assert "MEJORADA" in results.output

    def test_scores_ordenados(self):
        """Los scores deben estar presentes y ordenados."""
        results = voting(
            generator_fns=[_gen_better, _gen_ok],
            evaluator_fn=_evaluator,
            task="test",
        )
        assert len(results.scores) == 2
        assert results.scores[0] >= results.scores[-1]  # sorted desc


class TestCritiqueRevise:
    def test_acepta_sin_critica(self):
        """Si no hay critica, acepta en primera iteracion."""
        def no_critic(task, result):
            return ""
        result = critique_revise(
            generator_fn=_gen_ok,
            critic_fn=no_critic,
            task="test",
        )
        assert result.success is True
        assert result.iterations == 1

    def test_revisa_con_critica(self):
        """Si hay critica, itera hasta mejorarla."""
        def gen_with_fix(task: str) -> str:
            if "Falta" in task:
                return "solucion TODO: mejorar validacion"
            return "solucion mejorada con validacion"
        result = critique_revise(
            generator_fn=gen_with_fix,
            critic_fn=_critic,
            task="test",
            max_iterations=3,
        )
        assert result.success is True


class TestParallelTransform:
    def test_mergea_resultados(self):
        """Parallel-Transform debe mergear todos los partials."""
        result = parallel_transform(
            transform_fns=[_gen_ok, _gen_better],
            merge_fn=_merge,
            task="test",
        )
        assert result.success is True
        assert "---" in result.output  # separador del merge

    def test_traces_por_transformador(self):
        """Cada transformador debe tener un trace."""
        result = parallel_transform(
            transform_fns=[_gen_ok],
            merge_fn=_merge,
            task="test",
        )
        assert len(result.traces) >= 1
        assert result.traces[0]["transformer"] == 0
