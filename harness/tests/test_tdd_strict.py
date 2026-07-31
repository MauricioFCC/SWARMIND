"""
Tests para el workflow TDD estricto (ADR-0033): Spec-First, Code-Second.

Cubre: estructura del DAG (3 niveles y agentes), reglas de oro de TDDPhase,
validacion determinista de TDDGate por fase y el render del
TestConfidenceReport (formato exacto, veredicto de mutation, PBT con fallos).
"""

from __future__ import annotations

import pytest

from harness.orchestrator.workflows.tdd_strict import (
    TDDGate,
    TDDPhase,
    TDDStrictDAG,
    TestConfidenceReport,
    build_tdd_dag,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_report() -> TestConfidenceReport:
    """Reporte de confianza con las metricas del ejemplo del ADR-0033."""
    return TestConfidenceReport(
        tests_passed=142,
        tests_total=142,
        pbt_generations=5000,
        pbt_failures=0,
        mutation_score=88.5,
        surviving_mutants=12,
        branch_coverage=96.2,
        sandbox_iterations=4,
        sandbox_duration_seconds=192.0,
        files_modified=["src/core/a.py", "src/core/b.py", "src/api/c.py"],
    )


# ---------------------------------------------------------------------------
# DAG: estructura y validacion
# ---------------------------------------------------------------------------


def test_dag_has_three_levels_with_correct_agents() -> None:
    """El DAG tiene 3 niveles con los agentes scientist/guardian, builder/guardian, coordinator."""
    dag = build_tdd_dag()

    assert dag["name"] == "tdd_strict"
    assert len(dag["levels"]) == 3
    assert [level["level"] for level in dag["levels"]] == [0, 1, 2]
    assert dag["levels"][0]["agents"] == ["scientist", "guardian"]
    assert dag["levels"][1]["agents"] == ["builder", "guardian"]
    assert dag["levels"][2]["agents"] == ["coordinator"]
    assert dag["levels"][0]["phase"] == "RED"
    assert dag["levels"][1]["phase"] == "GREEN"


def test_dag_validate_accepts_canonical_structure() -> None:
    """La estructura canonica del DAG se valida como correcta."""
    ok, message = TDDStrictDAG().validate()

    assert ok is True
    assert message


def test_dag_validate_rejects_wrong_name() -> None:
    """Un DAG con nombre distinto a tdd_strict se rechaza en validacion."""
    dag = TDDStrictDAG(name="otro_workflow")

    ok, message = dag.validate()

    assert ok is False
    assert "name" in message


def test_phase_prohibitions_declared() -> None:
    """TDDPhase declara las tres prohibiciones de oro del ciclo TDD."""
    assert TDDPhase.RED.prohibition.startswith("PROHIBIDO implementar")
    assert TDDPhase.GREEN.prohibition.startswith("PROHIBIDO tocar el test")
    assert TDDPhase.REFACTOR.prohibition.startswith("PROHIBIDO cambiar comportamiento")


# ---------------------------------------------------------------------------
# TDDGate: validacion determinista por fase
# ---------------------------------------------------------------------------


def test_gate_fails_red_when_src_modified() -> None:
    """En RED el gate FALLA si se modifico src/ (prohibido implementar)."""
    gate = TDDGate()

    ok, message = gate.validate_phase(
        TDDPhase.RED, test_files_modified=True, src_files_modified=True
    )

    assert ok is False
    assert "RED" in message
    assert "src/" in message


def test_gate_allows_red_when_only_tests_modified() -> None:
    """En RED escribir solo tests es la tarea correcta y pasa el gate."""
    ok, message = TDDGate().validate_phase(
        TDDPhase.RED, test_files_modified=True, src_files_modified=False
    )

    assert ok is True
    assert message


def test_gate_blocks_builder_when_touching_tests_in_green() -> None:
    """En GREEN el builder nunca toca tests: el gate FALLA si los modifico."""
    gate = TDDGate()

    ok, message = gate.validate_phase(
        TDDPhase.GREEN, test_files_modified=True, src_files_modified=True
    )

    assert ok is False
    assert "GREEN" in message
    assert "test" in message.lower()


def test_gate_allows_green_when_only_src_modified() -> None:
    """En GREEN implementar solo en src/ es la tarea correcta y pasa el gate."""
    ok, message = TDDGate().validate_phase(
        TDDPhase.GREEN, test_files_modified=False, src_files_modified=True
    )

    assert ok is True
    assert message


def test_gate_allows_refactor_changes_without_touching_tests() -> None:
    """En REFACTOR se permiten cambios en src/ siempre que no se toquen tests."""
    ok, message = TDDGate().validate_phase(
        TDDPhase.REFACTOR, test_files_modified=False, src_files_modified=True
    )

    assert ok is True
    assert message


def test_gate_fails_refactor_when_tests_touched() -> None:
    """En REFACTOR tocar tests es una violacion y el gate FALLA."""
    ok, message = TDDGate().validate_phase(
        TDDPhase.REFACTOR, test_files_modified=True, src_files_modified=False
    )

    assert ok is False
    assert "REFACTOR" in message


# ---------------------------------------------------------------------------
# TestConfidenceReport: render
# ---------------------------------------------------------------------------


def test_report_renders_expected_format(sample_report: TestConfidenceReport) -> None:
    """El render produce EXACTAMENTE el formato del ADR-0033 sin mostrar codigo."""
    expected = "\n".join(
        [
            "✅ ESPECIFICACIÓN APROBADA (Fuente Única de Verdad)",
            "📊 Métricas de Confianza:",
            "   • Tests Unitarios: 142/142 Passing (100%)",
            "   • Property-Based Testing (PBT): 5,000 generaciones sin fallos.",
            "   • Mutation Score: 88.5% (Robusto, 12 mutantes supervivientes aceptados como riesgo conocido).",
            "   • Cobertura de Ramas Lógicas: 96.2%",
            "⏱️ Ciclo Autónomo: 4 iteraciones en el SandboxLoop (3 min 12 seg).",
            "🛡️ Archivos modificados: 3 en `src/` (Ocultos. Usa `!show code` solo si es estrictamente necesario para debug).",
        ]
    )

    assert sample_report.render() == expected


def test_report_mutation_below_85_requires_reinforcement() -> None:
    """Mutation score < 85 cambia el veredicto a 'Requiere refuerzo'."""
    report = TestConfidenceReport(
        tests_passed=10,
        tests_total=10,
        pbt_generations=100,
        pbt_failures=0,
        mutation_score=84.9,
        surviving_mutants=31,
        branch_coverage=70.0,
        sandbox_iterations=1,
        files_modified=["src/x.py"],
    )

    rendered = report.render()

    assert "Requiere refuerzo" in rendered
    assert "Robusto" not in rendered
    assert "84.9%" in rendered


def test_report_pass_rate_and_counts_are_parametric() -> None:
    """Pass rate, generaciones y archivos se calculan de los valores recibidos."""
    report = TestConfidenceReport(
        tests_passed=3,
        tests_total=4,
        pbt_generations=1000,
        pbt_failures=0,
        mutation_score=90.0,
        surviving_mutants=2,
        branch_coverage=80.0,
        sandbox_iterations=2,
        files_modified=["src/a.py", "src/b.py"],
    )

    rendered = report.render()

    assert "3/4 Passing (75%)" in rendered
    assert "1,000 generaciones" in rendered
    assert "2 en `src/`" in rendered
    assert "2 iteraciones en el SandboxLoop (3 min 12 seg)" in rendered


def test_report_pbt_failures_are_reported() -> None:
    """Si pbt_failures > 0 el reporte lo indica y no dice 'sin fallos'."""
    report = TestConfidenceReport(
        tests_passed=9,
        tests_total=10,
        pbt_generations=5000,
        pbt_failures=2,
        mutation_score=88.5,
        surviving_mutants=12,
        branch_coverage=96.2,
        sandbox_iterations=4,
        files_modified=["src/a.py"],
    )

    rendered = report.render()

    assert "sin fallos" not in rendered
    assert "2 fallos detectados" in rendered


def test_report_pbt_singular_failure() -> None:
    """Un solo fallo de PBT se reporta en singular."""
    report = TestConfidenceReport(
        tests_passed=10,
        tests_total=10,
        pbt_generations=5000,
        pbt_failures=1,
        mutation_score=95.0,
        surviving_mutants=1,
        branch_coverage=90.0,
        sandbox_iterations=2,
        files_modified=[],
    )

    assert "1 fallo detectado" in report.render()
