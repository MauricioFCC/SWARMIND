"""Tests TDD para ``harness.evals.consistency`` (consistencia run-to-run).

Tecnica frontera (arXiv:2607.27942, guia #4): medir la consistencia run-to-run
JUNTO a la accuracy. Un sistema con buena accuracy media pero que no resuelve
confiablemente una misma tarea tiene valor de produccion limitado. Aqui se mide
el pass rate de ``runs`` corridas deterministas y su varianza Bernoulli p(1-p)
(proxy de la varianza run-to-run). Todos los runners son mocks deterministas:
0 LLM, 0 red, 0 DB.

Cobertura:
    (a) runner siempre pasa    -> p=1.0, var=0.0, "stable", stable True.
    (b) runner siempre falla   -> p=0.0, "broken".
    (c) runner alterna (mitad) -> "flaky", var ~0.25.
    (d) evaluate respeta runs  -> spy: # llamadas == runs.
    (e) report: consistency_score = stable/total; mean_variance correcto.
    (f) sentinela de mutacion: invertir el comparador de veredicto lo rompe.
    (g) umbrales configurables -> stability_threshold=0.8 hace 0.9 "stable".
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator

import pytest

from harness.evals.consistency import (
    DEFAULT_FLAKY_THRESHOLD,
    DEFAULT_RUNS,
    DEFAULT_STABILITY_THRESHOLD,
    ConsistencyEvaluator,
    ConsistencyResult,
)

# ---------------------------------------------------------------------------
# Runners mock reutilizables (DI: runner(task_id) -> bool)
# ---------------------------------------------------------------------------


def _runner_always_true(task_id: str) -> bool:
    """Pasa siempre (sistema estable)."""
    return True


def _runner_always_false(task_id: str) -> bool:
    """Falla siempre (sistema roto)."""
    return False


def _make_alternating_evaluator() -> ConsistencyEvaluator:
    """Crea un evaluador cuyo runner alterna True/False (pass rate exacto = 0.5).

    Returns:
        ``ConsistencyEvaluator`` con un ``itertools.cycle`` fresco por test para
        no compartir estado entre pruebas.
    """
    cycle: Iterator[bool] = itertools.cycle([True, False])
    return ConsistencyEvaluator(runner=lambda task_id: next(cycle))


# ---------------------------------------------------------------------------
# Contrato del dataclass y constantes
# ---------------------------------------------------------------------------


class TestConsistencyResultContract:
    """Contrato basico del dataclass congelado ConsistencyResult."""

    def test_frozen_dataclass(self) -> None:
        """ConsistencyResult es inmutable."""
        result = ConsistencyResult(
            task_id="t1",
            runs=1,
            passes=1,
            pass_rate=1.0,
            variance=0.0,
            stable=True,
            verdict="stable",
        )
        with pytest.raises((AttributeError, TypeError)):
            result.task_id = "otro"  # type: ignore[misc]

    def test_default_notes_vacio(self) -> None:
        """notes tiene default vacio para construccion minima."""
        result = ConsistencyResult("t1", 1, 1, 1.0, 0.0, True, "stable")
        assert result.notes == ""


class TestConstants:
    """Constantes publicas del modulo."""

    def test_default_thresholds(self) -> None:
        """Umbrales por defecto: stable 0.95, broken 0.5."""
        assert DEFAULT_STABILITY_THRESHOLD == 0.95
        assert DEFAULT_FLAKY_THRESHOLD == 0.5

    def test_default_runs(self) -> None:
        """DEFAULT_RUNS es 10."""
        assert DEFAULT_RUNS == 10


# ---------------------------------------------------------------------------
# Casos (a), (b), (c): el pass rate determina el veredicto
# ---------------------------------------------------------------------------


class TestVerdicts:
    """Casos (a) estable, (b) roto y (c) flaky."""

    def test_a_runner_siempre_pasa_es_stable(self) -> None:
        """(a) Runner siempre True -> p=1.0, var=0.0, verdict stable."""
        evaluator = ConsistencyEvaluator(runner=_runner_always_true)
        result = evaluator.evaluate("t1", runs=10)

        assert result.pass_rate == 1.0
        assert result.passes == 10
        assert result.variance == 0.0
        assert result.verdict == "stable"
        assert result.stable is True

    def test_b_runner_siempre_falla_es_broken(self) -> None:
        """(b) Runner siempre False -> p=0.0, verdict broken."""
        evaluator = ConsistencyEvaluator(runner=_runner_always_false)
        result = evaluator.evaluate("t1", runs=10)

        assert result.pass_rate == 0.0
        assert result.passes == 0
        assert result.verdict == "broken"
        assert result.stable is False

    def test_c_runner_alterna_es_flaky(self) -> None:
        """(c) Runner que pasa la mitad -> verdict flaky, var ~0.25."""
        evaluator = _make_alternating_evaluator()
        result = evaluator.evaluate("t1", runs=10)

        assert result.pass_rate == 0.5
        assert result.passes == 5
        assert result.variance == pytest.approx(0.25)
        assert result.verdict == "flaky"
        assert result.stable is False


# ---------------------------------------------------------------------------
# Caso (d): contabilidad de corridas
# ---------------------------------------------------------------------------


class TestRunsAccounting:
    """Caso (d): evaluate respeta el numero de corridas."""

    def test_d_evaluate_respeta_runs(self) -> None:
        """(d) spy: # llamadas al runner == runs."""
        calls: list[str] = []

        def spy_runner(task_id: str) -> bool:
            calls.append(task_id)
            return True

        evaluator = ConsistencyEvaluator(runner=spy_runner)
        evaluator.evaluate("t1", runs=7)

        assert len(calls) == 7
        assert all(task_id == "t1" for task_id in calls)

    def test_d_default_runs_se_aplica(self) -> None:
        """(d) sin argumento runs se usa DEFAULT_RUNS."""
        counter = {"n": 0}

        def spy_runner(task_id: str) -> bool:
            counter["n"] += 1
            return True

        ConsistencyEvaluator(runner=spy_runner).evaluate("t1")
        assert counter["n"] == DEFAULT_RUNS


# ---------------------------------------------------------------------------
# Caso (e): agregacion del reporte
# ---------------------------------------------------------------------------


class TestReportAggregation:
    """Caso (e): consistency_score y mean_variance."""

    def test_e_consistency_score_y_mean_variance(self) -> None:
        """(e) 1 stable de 3 -> consistency_score ~= 0.3333; mean_var ~= 0.0833."""
        stable = ConsistencyEvaluator(runner=_runner_always_true).evaluate("s", runs=10)
        broken = ConsistencyEvaluator(runner=_runner_always_false).evaluate("b", runs=10)
        evaluator = _make_alternating_evaluator()
        flaky = evaluator.evaluate("f", runs=10)

        runner_for_report = ConsistencyEvaluator(runner=_runner_always_true)
        summary = runner_for_report.report([stable, flaky, broken])

        assert summary["stable"] == 1
        assert summary["flaky"] == 1
        assert summary["broken"] == 1
        # El reporte redondea a 4 decimales (coherente con skill_lift): abs=1e-4.
        assert summary["consistency_score"] == pytest.approx(1 / 3, abs=1e-4)
        # mean_variance = (0.0 + 0.25 + 0.0) / 3
        assert summary["mean_variance"] == pytest.approx(0.25 / 3, abs=1e-4)
        assert summary["mean_pass_rate"] == pytest.approx((1.0 + 0.5 + 0.0) / 3, abs=1e-4)

    def test_e_consistency_score_todos_stable(self) -> None:
        """(e) si todas las tareas son stable -> consistency_score == 1.0."""
        evaluator = ConsistencyEvaluator(runner=_runner_always_true)
        results = evaluator.evaluate_all(["t1", "t2", "t3"], runs=5)
        summary = evaluator.report(results)

        assert summary["consistency_score"] == 1.0
        assert summary["mean_variance"] == 0.0

    def test_e_report_vacio(self) -> None:
        """(e) report sin resultados -> todo 0.0."""
        evaluator = ConsistencyEvaluator(runner=_runner_always_true)
        assert evaluator.report([]) == {
            "stable": 0,
            "flaky": 0,
            "broken": 0,
            "mean_pass_rate": 0.0,
            "mean_variance": 0.0,
            "consistency_score": 0.0,
        }


class TestEvaluateAll:
    """evaluate_all preserva el orden y el numero de tareas."""

    def test_evaluate_all_orden_preservado(self) -> None:
        """Devuelve un resultado por tarea, en el mismo orden de entrada."""
        evaluator = ConsistencyEvaluator(runner=_runner_always_true)
        results = evaluator.evaluate_all(["alpha", "beta"], runs=3)

        assert [r.task_id for r in results] == ["alpha", "beta"]
        assert all(r.verdict == "stable" for r in results)


# ---------------------------------------------------------------------------
# Caso (f): sentinela de mutacion
# ---------------------------------------------------------------------------


class TestVerdictMutationSentinel:
    """Caso (f): sentinela de mutacion del clasificador de veredicto.

    Si un mutante invierte el comparador de verdicto (``>=`` <-> ``<=`` o el
    orden stable/broken), un sistema 100% estable dejaria de clasificarse
    "stable" y/o uno 0% dejaria de clasificarse "broken"; estos asserts fallan.
    """

    def test_f_comparador_observable_en_extremos(self) -> None:
        """Extremo alto -> stable; extremo bajo -> broken (comparador invertido falla)."""
        always_pass = ConsistencyEvaluator(runner=_runner_always_true).evaluate("t1", runs=10)
        always_fail = ConsistencyEvaluator(runner=_runner_always_false).evaluate("t1", runs=10)

        assert always_pass.verdict == "stable"
        assert always_pass.stable is True
        assert always_fail.verdict == "broken"
        assert always_fail.stable is False
        # Un mutante que invierta el comparador romperia el mapeo p->verdict.
        assert always_pass.verdict != always_fail.verdict


# ---------------------------------------------------------------------------
# Caso (g): umbrales configurables
# ---------------------------------------------------------------------------


class TestConfigurableThresholds:
    """Caso (g): los umbrales son inyectables."""

    def test_g_stability_threshold_080_hace_090_stable(self) -> None:
        """(g) con stability_threshold=0.8 un pass rate de 0.9 es stable."""
        counter = {"n": 0}

        def nine_of_ten(task_id: str) -> bool:
            counter["n"] += 1
            return counter["n"] <= 9

        evaluator = ConsistencyEvaluator(runner=nine_of_ten, stability_threshold=0.8)
        result = evaluator.evaluate("t1", runs=10)

        assert result.pass_rate == pytest.approx(0.9)
        assert result.verdict == "stable"

    def test_g_con_default_090_seria_flaky(self) -> None:
        """(g) contraprueba: con el umbral por defecto (0.95), 0.9 -> flaky."""
        counter = {"n": 0}

        def nine_of_ten(task_id: str) -> bool:
            counter["n"] += 1
            return counter["n"] <= 9

        result = ConsistencyEvaluator(runner=nine_of_ten).evaluate("t1", runs=10)

        assert result.pass_rate == pytest.approx(0.9)
        assert result.verdict == "flaky"


# ---------------------------------------------------------------------------
# Guardrails de entrada (VAL)
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Validacion de entradas y umbrales."""

    def test_task_id_vacio_falla(self) -> None:
        """task_id vacio -> ValueError."""
        evaluator = ConsistencyEvaluator(runner=_runner_always_true)
        with pytest.raises(ValueError):
            evaluator.evaluate("  ")

    def test_runs_invalido_falla(self) -> None:
        """runs < 1 -> ValueError."""
        evaluator = ConsistencyEvaluator(runner=_runner_always_true)
        with pytest.raises(ValueError):
            evaluator.evaluate("t1", runs=0)

    def test_runner_no_callable_falla(self) -> None:
        """runner no callable -> TypeError."""
        with pytest.raises(TypeError):
            ConsistencyEvaluator(runner="no-soy-callable")  # type: ignore[arg-type]

    def test_threshold_fuera_de_rango_falla(self) -> None:
        """Umbral fuera de [0,1] -> ValueError."""
        with pytest.raises(ValueError):
            ConsistencyEvaluator(runner=_runner_always_true, stability_threshold=1.5)

    def test_thresholds_invertidos_falla(self) -> None:
        """flaky_threshold > stability_threshold -> ValueError."""
        with pytest.raises(ValueError):
            ConsistencyEvaluator(
                runner=_runner_always_true,
                stability_threshold=0.4,
                flaky_threshold=0.5,
            )

    def test_evaluate_all_vacio_falla(self) -> None:
        """evaluate_all con lista vacia -> ValueError."""
        evaluator = ConsistencyEvaluator(runner=_runner_always_true)
        with pytest.raises(ValueError):
            evaluator.evaluate_all([])
