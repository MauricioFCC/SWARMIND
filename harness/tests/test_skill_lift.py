"""Tests TDD para ``harness.evals.skill_lift`` (Paired Evaluation / Skill Lift).

Tecnica frontera (SkillsBench, arXiv:2602.12670): medir el delta de pass rate
en puntos porcentuales (Δpp) con/sin skill sobre las MISMAS tareas. Solo las
skills con lift > 0 se conservan. Todos los runners son mocks deterministas:
0 LLM, 0 red, 0 DB.

Cobertura:
    (a) skill siempre ayuda  -> Δ +100pp, "useful".
    (b) skill indiferente     -> Δ 0pp,    "neutral".
    (c) skill perjudica       -> Δ negativo, "harmful".
    (d) evaluate respeta trials (spy: # llamadas = len(tasks) * trials * 2).
    (e) evaluate_all ordenado por delta desc.
    (f) sentinela de mutacion: el signo del verdict es observable (useful<->harmful).
    (g) banda neutra: Δ +0.5pp -> "neutral" (dentro de NEUTRAL_BAND_PP).
"""

from __future__ import annotations

import pytest

from harness.evals.skill_lift import (
    DEFAULT_TRIALS,
    NEUTRAL_BAND_PP,
    LiftResult,
    SkillLiftEvaluator,
)

# ---------------------------------------------------------------------------
# Runners mock reutilizables (DI: runner(task_id, skill | None) -> bool)
# ---------------------------------------------------------------------------


def _runner_always_with_only(task_id: str, skill: str | None) -> bool:
    """Pasa SOLO cuando hay skill activa; falla siempre en ablacion."""
    return skill == "helpful"


def _runner_indifferent(task_id: str, skill: str | None) -> bool:
    """Pasa siempre, con o sin skill (sin efecto de la skill)."""
    return True


def _runner_worse_with_skill(task_id: str, skill: str | None) -> bool:
    """Falla cuando hay skill activa; pasa en ablacion (skill danina)."""
    return skill is None


def _ablation(task_id: str) -> bool:
    """Patron base de la condicion sin skill (ablacion compartida)."""
    return task_id == "t1"


class TestLiftResultContract:
    """Contrato basico del dataclass congelado LiftResult."""

    def test_frozen_dataclass(self) -> None:
        """LiftResult es inmutable."""
        result = LiftResult(
            skill="s",
            trials=1,
            pass_with=1.0,
            pass_without=0.0,
            delta_pp=100.0,
            verdict="useful",
            notes="",
        )
        with pytest.raises((AttributeError, TypeError)):
            result.skill = "otro"  # type: ignore[misc]

    def test_default_notes_vacio(self) -> None:
        """notes tiene default vacio para construccion minima."""
        result = LiftResult(
            skill="s",
            trials=1,
            pass_with=1.0,
            pass_without=0.0,
            delta_pp=100.0,
            verdict="useful",
        )
        assert result.notes == ""


class TestSkillLiftHelpers:
    """Constantes publicas del modulo."""

    def test_default_trials(self) -> None:
        """DEFAULT_TRIALS es 5 (pass@trials por condicion)."""
        assert DEFAULT_TRIALS == 5

    def test_neutral_band(self) -> None:
        """NEUTRAL_BAND_PP es 1.0 pp."""
        assert NEUTRAL_BAND_PP == 1.0


class TestSkillLiftDeltaSigns:
    """Casos (a), (b), (c): signo del delta determina el verdict."""

    def test_a_skill_helpful_delta_100_useful(self) -> None:
        """(a) Runner que pasa solo con skill -> Δ +100pp y verdict useful."""
        evaluator = SkillLiftEvaluator(runner=_runner_always_with_only)
        result = evaluator.evaluate("helpful", ["t1", "t2", "t3"], trials=2)

        assert result.pass_with == 1.0
        assert result.pass_without == 0.0
        assert result.delta_pp == pytest.approx(100.0)
        assert result.verdict == "useful"
        assert result.trials == 2

    def test_b_skill_indifferent_delta_0_neutral(self) -> None:
        """(b) Runner constante -> Δ 0pp y verdict neutral."""
        evaluator = SkillLiftEvaluator(runner=_runner_indifferent)
        result = evaluator.evaluate("meh", ["t1", "t2"], trials=3)

        assert result.pass_with == result.pass_without == 1.0
        assert result.delta_pp == pytest.approx(0.0)
        assert result.verdict == "neutral"

    def test_c_skill_harmful_delta_negative(self) -> None:
        """(c) Runner que empeora con skill -> Δ negativo y verdict harmful."""
        evaluator = SkillLiftEvaluator(runner=_runner_worse_with_skill)
        result = evaluator.evaluate("bad", ["t1", "t2"], trials=2)

        assert result.pass_with == 0.0
        assert result.pass_without == 1.0
        assert result.delta_pp == pytest.approx(-100.0)
        assert result.verdict == "harmful"


class TestTrialsAccounting:
    """Caso (d): el numero de llamadas respeta trials y ambas condiciones."""

    def test_d_evaluate_respeta_trials(self) -> None:
        """(d) spy: # llamadas = len(tasks) * trials * 2 (con y sin skill)."""
        calls: list[tuple[str, str | None]] = []

        def spy_runner(task_id: str, skill: str | None) -> bool:
            calls.append((task_id, skill))
            return True

        tasks = ["t1", "t2", "t3"]
        trials = 4
        evaluator = SkillLiftEvaluator(runner=spy_runner)
        evaluator.evaluate("s", tasks, trials=trials)

        assert len(calls) == len(tasks) * trials * 2
        # La condicion con skill usa el nombre; la ablacion usa None.
        assert any(skill == "s" for _, skill in calls)
        assert any(skill is None for _, skill in calls)

    def test_d_default_trials_se_aplica(self) -> None:
        """(d) sin argumento trials se usa DEFAULT_TRIALS."""
        counter = {"n": 0}

        def spy_runner(task_id: str, skill: str | None) -> bool:
            counter["n"] += 1
            return True

        evaluator = SkillLiftEvaluator(runner=spy_runner)
        evaluator.evaluate("s", ["t1", "t2"])

        assert counter["n"] == 2 * DEFAULT_TRIALS * 2


class TestEvaluateAllOrdering:
    """Caso (e): evaluate_all ordena por delta descendente."""

    def test_e_ordenado_por_delta_desc(self) -> None:
        """(e) devuelve useful, neutral, harmful en ese orden."""

        def ranked_runner(task_id: str, skill: str | None) -> bool:
            if skill == "best":
                return True  # siempre pasa con skill -> lift positivo
            if skill == "worst":
                return False  # siempre falla con skill -> lift negativo
            return _ablation(task_id)  # neutral reproduce la ablacion (delta 0)

        evaluator = SkillLiftEvaluator(runner=ranked_runner)
        results = evaluator.evaluate_all(["worst", "neutral", "best"], ["t1", "t2"], trials=2)

        assert [r.skill for r in results] == ["best", "neutral", "worst"]
        deltas = [r.delta_pp for r in results]
        assert deltas == sorted(deltas, reverse=True)


class TestVerdictBoundary:
    """Caso (g): banda neutra NEUTRAL_BAND_PP."""

    def test_g_delta_positivo_dentro_de_banda_es_neutral(self) -> None:
        """(g) Δ +0.5pp (|Δ| < 1pp) -> verdict neutral."""
        calls: dict[tuple[str, str | None], int] = {}

        def nuanced_runner(task_id: str, skill: str | None) -> bool:
            key = (task_id, skill)
            seen = calls.get(key, 0)
            calls[key] = seen + 1
            # Sin skill, t2 falla en su primera corrida -> pass_without=0.995
            if skill is None and task_id == "t2":
                return seen != 0
            return True

        evaluator = SkillLiftEvaluator(runner=nuanced_runner)
        result = evaluator.evaluate("borderline", ["t1", "t2"], trials=100)

        assert abs(result.delta_pp) < NEUTRAL_BAND_PP
        assert result.delta_pp == pytest.approx(0.5)
        assert result.verdict == "neutral"


class TestVerdictMutationSentinel:
    """Caso (f): test sentinela de mutacion del signo del verdict.

    Si un mutante invierte la comparacion del clasificador (``>`` <-> ``<``),
    util y danino se intercambian y estos asserts fallan. El umbral de banda
    tambien se verifica en ambos extremos.
    """

    def test_f_signo_observable_en_ambos_extremos(self) -> None:
        """Util positivo es 'useful'; danino negativo es 'harmful'."""
        useful = SkillLiftEvaluator(runner=_runner_always_with_only).evaluate("helpful", ["t1"])
        harmful = SkillLiftEvaluator(runner=_runner_worse_with_skill).evaluate("bad", ["t1"])

        assert useful.delta_pp > 0
        assert useful.verdict == "useful"
        assert harmful.delta_pp < 0
        assert harmful.verdict == "harmful"
        # Un mutante de signo invertiria estos dos y romperia el test.
        assert useful.verdict != harmful.verdict


class TestInputValidation:
    """Guardrails de entrada (VAL)."""

    def test_skill_vacio_falla(self) -> None:
        """Skill vacia -> ValueError."""
        evaluator = SkillLiftEvaluator(runner=_runner_indifferent)
        with pytest.raises(ValueError):
            evaluator.evaluate("  ", ["t1"])

    def test_tasks_vacio_falla(self) -> None:
        """Lista de tareas vacia -> ValueError."""
        evaluator = SkillLiftEvaluator(runner=_runner_indifferent)
        with pytest.raises(ValueError):
            evaluator.evaluate("s", [])

    def test_trials_invalido_falla(self) -> None:
        """trials < 1 -> ValueError."""
        evaluator = SkillLiftEvaluator(runner=_runner_indifferent)
        with pytest.raises(ValueError):
            evaluator.evaluate("s", ["t1"], trials=0)


class TestReportAggregation:
    """report(results) agrega por verdictos."""

    def test_report_counts_y_media(self) -> None:
        """report resume useful/neutral/harmful y media de delta."""
        evaluator = SkillLiftEvaluator(runner=_runner_indifferent)
        results = [
            LiftResult("a", 1, 1.0, 0.0, 100.0, "useful"),
            LiftResult("b", 1, 1.0, 1.0, 0.0, "neutral"),
            LiftResult("c", 1, 0.0, 1.0, -100.0, "harmful"),
        ]

        summary = evaluator.report(results)

        assert summary["useful"] == 1
        assert summary["neutral"] == 1
        assert summary["harmful"] == 1
        assert summary["mean_delta_pp"] == pytest.approx(0.0)

    def test_report_vacio(self) -> None:
        """report sin resultados -> conteos 0 y media 0.0."""
        evaluator = SkillLiftEvaluator(runner=_runner_indifferent)
        summary = evaluator.report([])
        assert summary == {"useful": 0, "neutral": 0, "harmful": 0, "mean_delta_pp": 0.0}
