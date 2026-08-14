"""
Tests para el H3 TestReinforcementLoop (arXiv 2607.23002, kill rate 78%).

Loop Tester -> mutation -> Critic que refuerza los tests para matar mutantes
supervivientes. Cubre: umbral de refuerzo (85.0), generacion de SPEC de tests
dirigidos, simulacion del loop con oraculo mecanico (kill rate incremental),
clamp de rounds y de score, render de reportes/guia y la conexion con el
veredicto de tdd_strict ("Robusto"/"Requiere refuerzo").
"""

from __future__ import annotations

import pytest

from harness.orchestrator.workflows.test_reinforcement import (
    SurvivingMutant,
    TestReinforcementLoop,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_mutants() -> tuple[SurvivingMutant, ...]:
    """Dos mutantes supervivientes tipicos detectados por mutation testing."""
    return (
        SurvivingMutant(
            mutant_id="mut_01",
            src_path="src/game/adivina.py",
            line=42,
            description="cambió `>` por `<`",
        ),
        SurvivingMutant(
            mutant_id="mut_02",
            src_path="src/game/puntaje.py",
            line=17,
            description="eliminó el `return` de la rama else",
        ),
    )


# ---------------------------------------------------------------------------
# needs_reinforcement: umbral MUTATION_TARGET = 85.0
# ---------------------------------------------------------------------------


def test_needs_reinforcement_below_threshold() -> None:
    """Un mutation score de 50 esta por debajo del umbral: exige refuerzo."""
    assert TestReinforcementLoop().needs_reinforcement(50.0) is True


def test_needs_reinforcement_at_threshold() -> None:
    """Un mutation score de 85 en el umbral NO exige refuerzo (>= target)."""
    assert TestReinforcementLoop().needs_reinforcement(85.0) is False


def test_needs_reinforcement_above_threshold() -> None:
    """Un mutation score de 90 por encima del umbral NO exige refuerzo."""
    assert TestReinforcementLoop().needs_reinforcement(90.0) is False


def test_needs_reinforcement_perfect_score() -> None:
    """Un mutation score perfecto de 100 NO exige refuerzo."""
    assert TestReinforcementLoop().needs_reinforcement(100.0) is False


# ---------------------------------------------------------------------------
# suggest_tests_for_mutants: generador de SPEC dirigidas
# ---------------------------------------------------------------------------


def test_suggest_tests_empty_mutants_returns_empty() -> None:
    """Sin mutantes supervivientes no se generan sugerencias de tests."""
    assert TestReinforcementLoop().suggest_tests_for_mutants(()) == ()


def test_suggest_tests_two_mutants_yield_two_suggestions_with_location(
    sample_mutants: tuple[SurvivingMutant, ...],
) -> None:
    """Cada mutante produce una sugerencia con 'Test' y su src_path/line."""
    loop = TestReinforcementLoop()

    suggestions = loop.suggest_tests_for_mutants(sample_mutants)

    assert len(suggestions) == 2
    for suggestion, mutant in zip(suggestions, sample_mutants, strict=True):
        assert suggestion.startswith("Test ")
        assert mutant.src_path in suggestion
        assert str(mutant.line) in suggestion


# ---------------------------------------------------------------------------
# reinforce: oraculo mecanico con kill rate incremental
# ---------------------------------------------------------------------------


def test_reinforce_improves_score_and_targets_mutants(
    sample_mutants: tuple[SurvivingMutant, ...],
) -> None:
    """Score bajo + mutantes: improved True, final sube y objetivos correctos."""
    report = TestReinforcementLoop().reinforce(70.0, sample_mutants)

    assert report.improved is True
    assert report.final_score > report.initial_score
    assert report.mutants_targeted == 2
    assert len(report.tests_added) == 2
    assert report.final_score == pytest.approx(85.0)


def test_reinforce_no_mutants_no_improvement() -> None:
    """Sin mutantes el score no cambia y no mejora si sigue bajo el umbral."""
    report = TestReinforcementLoop().reinforce(60.0, ())

    assert report.final_score == report.initial_score == 60.0
    assert report.improved is False
    assert report.mutants_targeted == 0
    assert report.tests_added == ()


def test_reinforce_respects_max_rounds(
    sample_mutants: tuple[SurvivingMutant, ...],
) -> None:
    """El loop nunca itera mas alla de MAX_ROUNDS (score acotado por 3 rondas)."""
    report = TestReinforcementLoop().reinforce(30.0, sample_mutants, rounds=100)

    # 30 + (0.5 * 10) * 3 = 45.0: las rondas extra se ignoran.
    assert report.final_score == pytest.approx(45.0)


def test_reinforce_final_score_clamped_to_100(
    sample_mutants: tuple[SurvivingMutant, ...],
) -> None:
    """El score final nunca supera 100 aunque la mejora teorica lo exceda."""
    report = TestReinforcementLoop().reinforce(95.0, sample_mutants)

    assert report.final_score == 100.0
    assert report.improved is True


def test_reinforce_improved_false_below_target(
    sample_mutants: tuple[SurvivingMutant, ...],
) -> None:
    """Si el score final sigue por debajo de MUTATION_TARGET, improved es False."""
    report = TestReinforcementLoop().reinforce(50.0, sample_mutants)

    assert report.improved is False
    assert report.final_score == pytest.approx(65.0)
    assert report.final_score < TestReinforcementLoop.MUTATION_TARGET


def test_reinforce_zero_rounds_keeps_score(
    sample_mutants: tuple[SurvivingMutant, ...],
) -> None:
    """Con rounds=0 el score no cambia aunque haya mutantes objetivo."""
    report = TestReinforcementLoop().reinforce(70.0, sample_mutants, rounds=0)

    assert report.final_score == report.initial_score == 70.0
    assert report.improved is False
    assert report.mutants_targeted == 2


def test_reinforce_rounds_above_max_clamped(
    sample_mutants: tuple[SurvivingMutant, ...],
) -> None:
    """Rounds > MAX_ROUNDS se clampa: mismo resultado que con MAX_ROUNDS."""
    loop = TestReinforcementLoop()
    base = loop.reinforce(
        50.0, sample_mutants, rounds=TestReinforcementLoop.MAX_ROUNDS
    )
    extra = loop.reinforce(
        50.0, sample_mutants, rounds=TestReinforcementLoop.MAX_ROUNDS + 7
    )

    assert extra.final_score == base.final_score
    assert extra.tests_added == base.tests_added
    assert extra.improved == base.improved


# ---------------------------------------------------------------------------
# render_guidance: instrucciones accionables para el guardian
# ---------------------------------------------------------------------------


def test_render_guidance_includes_threshold_and_tests(
    sample_mutants: tuple[SurvivingMutant, ...],
) -> None:
    """La guia contiene el umbral pendiente y los tests a anadir."""
    loop = TestReinforcementLoop()
    report = loop.reinforce(70.0, sample_mutants)

    guidance = loop.render_guidance(report)

    assert f"{TestReinforcementLoop.MUTATION_TARGET:g}" in guidance
    assert "Test " in guidance
    assert "src/game/adivina.py:42" in guidance


# ---------------------------------------------------------------------------
# verdict_based_guidance: conexion con tdd_strict (sin modificarlo)
# ---------------------------------------------------------------------------


def test_verdict_guidance_robusto_when_above_threshold() -> None:
    """Score 90 reusa el veredicto 'Robusto' de tdd_strict."""
    guidance = TestReinforcementLoop().verdict_based_guidance(90.0, 0)

    assert "Robusto" in guidance


def test_verdict_guidance_requires_reinforcement_below_threshold() -> None:
    """Score 50 reusa 'Requiere refuerzo' y la guia apunta al reinforce()."""
    guidance = TestReinforcementLoop().verdict_based_guidance(50.0, 3)

    assert "Requiere refuerzo" in guidance
    assert "reinforce" in guidance.lower()


# ---------------------------------------------------------------------------
# Dataclasses: summary y render
# ---------------------------------------------------------------------------


def test_surviving_mutant_summary_readable() -> None:
    """El summary de un mutante es una linea legible con id y localizacion."""
    mutant = SurvivingMutant(
        mutant_id="mut_07",
        src_path="src/core/calc.py",
        line=99,
        description="cambió `>` por `<`",
    )

    summary = mutant.summary()

    assert "mut_07" in summary
    assert "src/core/calc.py" in summary
    assert "99" in summary


def test_reinforcement_report_render_not_empty(
    sample_mutants: tuple[SurvivingMutant, ...],
) -> None:
    """El render del reporte no es vacio e incluye el score final."""
    report = TestReinforcementLoop().reinforce(70.0, sample_mutants)

    rendered = report.render()

    assert rendered
    assert "85" in rendered
    assert report is not None
