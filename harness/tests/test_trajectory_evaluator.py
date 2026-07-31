"""
Tests para Agentic Trajectory Evaluator — evaluacion de la eficiencia del DAG.

Cubre:
  - Evaluacion sin redundancia -> OPTIMAL con redundancy_score 0.0
  - Deteccion de pasos consecutivos repetidos (mismo agente + misma accion)
  - Reintento tras fallo como redundancia parcial
  - Respeto del veredicto del LLM-as-judge custom
  - Conteo de agentes unicos y suma de duracion total
  - Construccion del prompt del judge (tarea, agentes, rubrica)
  - Resumen de una linea con el veredicto
  - Pasos vacios -> ValueError con WHAT+WHY+WHERE
  - Serializacion to_dict de TrajectoryStep y TrajectoryReport
  - Penalizacion por sobre-delegacion de agentes
"""

from __future__ import annotations

import json

import pytest

from harness.orchestrator.trajectory_evaluator import (
    TrajectoryEvaluator,
    TrajectoryReport,
    TrajectoryStep,
    build_judge_prompt,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _step(
    agent: str,
    action: str,
    duration_ms: float = 0.0,
    result: str = "success",
    output_tokens: int = 0,
    dependencies: list[str] | None = None,
) -> TrajectoryStep:
    """Crea un TrajectoryStep con defaults compactos para tests."""
    return TrajectoryStep(
        agent=agent,
        action=action,
        duration_ms=duration_ms,
        result=result,
        output_tokens=output_tokens,
        dependencies=dependencies or [],
    )


# ===========================================================================
# Tests: evaluacion basica
# ===========================================================================


class TestTrajectoryEvaluatorCore:
    """Tests del flujo principal de evaluate()."""

    def test_sin_redundancia_es_optimal(self):
        """Pasos distintos sin repeticiones dan redundancy 0 y OPTIMAL."""
        steps = [
            _step("coordinator", "plan", duration_ms=100.0),
            _step("builder", "write_code", duration_ms=250.0),
            _step("scientist", "validate", duration_ms=150.0),
        ]
        report = TrajectoryEvaluator().evaluate("task-opt", steps)
        assert report.redundancy_score == 0.0
        assert report.efficiency_score >= 80.0
        assert report.verdict == "OPTIMAL"
        assert report.steps == 3

    def test_pasos_consecutivos_repetidos_detectan_redundancia(self):
        """3 pasos consecutivos del mismo agente y accion son INEFFICIENT."""
        steps = [
            _step("builder", "write_code", duration_ms=100.0),
            _step("builder", "write_code", duration_ms=100.0),
            _step("builder", "write_code", duration_ms=100.0),
        ]
        report = TrajectoryEvaluator().evaluate("task-red", steps)
        assert report.redundancy_score > 0.0
        assert report.efficiency_score < 60.0
        assert report.verdict == "INEFFICIENT"
        assert any("builder" in rec for rec in report.recommendations)

    def test_reintento_tras_fallo_es_redundancia_parcial(self):
        """Un reintento tras fallo cuenta como redundancia parcial (< 1.0)."""
        steps = [
            _step("builder", "write_code", result="failed"),
            _step("builder", "write_code"),
        ]
        report = TrajectoryEvaluator().evaluate("task-retry", steps)
        assert report.redundancy_score == pytest.approx(0.75)
        assert report.verdict == "ACCEPTABLE"

    def test_sobre_delegacion_de_agentes_penaliza(self):
        """Mas de 4 agentes para pocos pasos resta 20 a la eficiencia."""
        steps = [
            _step("agent_a", "accion_a"),
            _step("agent_b", "accion_b"),
            _step("agent_c", "accion_c"),
            _step("agent_d", "accion_d"),
            _step("agent_e", "accion_e"),
        ]
        report = TrajectoryEvaluator().evaluate("task-over", steps)
        assert report.efficiency_score == pytest.approx(80.0)
        assert report.verdict == "OPTIMAL"
        assert any(rec.startswith("Reducir agentes de 5") for rec in report.recommendations)

    def test_agents_used_cuenta_unicos(self):
        """agents_used cuenta agentes distintos, no ocurrencias."""
        steps = [
            _step("builder", "design"),
            _step("builder", "write_code"),
            _step("scientist", "validate"),
            _step("builder", "write_code"),
        ]
        report = TrajectoryEvaluator().evaluate("task-agents", steps)
        assert report.agents_used == 2
        assert report.steps == 4

    def test_total_duration_ms_suma_duraciones(self):
        """total_duration_ms es la suma de todas las duraciones."""
        steps = [
            _step("coordinator", "plan", duration_ms=100.0),
            _step("builder", "write_code", duration_ms=250.5),
            _step("scientist", "validate", duration_ms=0.0),
        ]
        report = TrajectoryEvaluator().evaluate("task-dur", steps)
        assert report.total_duration_ms == pytest.approx(350.5)


# ===========================================================================
# Tests: LLM-as-judge
# ===========================================================================


class TestTrajectoryEvaluatorJudge:
    """Tests del modo LLM-as-a-Judge."""

    def test_evaluate_respeta_veredicto_del_judge_custom(self):
        """Un judge que devuelve INEFFICIENT impone su veredicto."""
        def judge(_prompt: str) -> str:
            return "INEFFICIENT: 5 agentes para 2 pasos"

        steps = [_step("coordinator", "plan"), _step("builder", "write_code")]
        report = TrajectoryEvaluator(judge=judge).evaluate("task-judge", steps)
        assert report.verdict == "INEFFICIENT"
        assert 0.0 <= report.efficiency_score <= 100.0
        assert report.efficiency_score < 60.0
        assert any("5 agentes para 2 pasos" in rec for rec in report.recommendations)

    def test_build_judge_prompt_contiene_tarea_agentes_y_rubrica(self):
        """El prompt del judge serializa la tarea, los agentes y la rubrica."""
        steps = [_step("builder", "write_code"), _step("coordinator", "plan")]
        prompt = build_judge_prompt("task-prompt", steps)
        assert "task-prompt" in prompt
        assert "builder" in prompt
        assert "coordinator" in prompt
        assert "RUBRICA" in prompt.upper()
        assert "INEFFICIENT" in prompt.upper()


# ===========================================================================
# Tests: salidas
# ===========================================================================


class TestTrajectoryEvaluatorOutputs:
    """Tests de summarize y serializacion."""

    def test_summarize_produce_resumen_con_veredicto(self):
        """summarize devuelve texto no vacio que incluye el veredicto."""
        evaluator = TrajectoryEvaluator()
        report = evaluator.evaluate("task-sum", [_step("builder", "write_code")])
        summary = evaluator.summarize(report)
        assert isinstance(summary, str)
        assert summary
        assert report.verdict in summary

    def test_step_to_dict_serializable(self):
        """TrajectoryStep.to_dict() expone todos los campos como dict."""
        step = TrajectoryStep(
            agent="builder",
            action="write_code",
            duration_ms=1.5,
            result="success",
            output_tokens=100,
            dependencies=["dep-a"],
        )
        assert step.to_dict() == {
            "agent": "builder",
            "action": "write_code",
            "duration_ms": 1.5,
            "result": "success",
            "output_tokens": 100,
            "dependencies": ["dep-a"],
        }

    def test_report_to_dict_serializable(self):
        """TrajectoryReport.to_dict() es un dict JSON-serializable."""
        report = TrajectoryEvaluator().evaluate("task-dict", [_step("builder", "write_code")])
        data = report.to_dict()
        assert isinstance(data, dict)
        assert data["task_id"] == "task-dict"
        assert data["steps"] == 1
        assert data["agents_used"] == 1
        assert data["verdict"] == "OPTIMAL"
        assert "redundancy_score" in data
        assert "efficiency_score" in data
        assert "recommendations" in data
        json.dumps(data)  # Debe ser JSON-serializable sin excepcion


# ===========================================================================
# Tests: casos borde
# ===========================================================================


class TestTrajectoryEvaluatorEdgeCases:
    """Tests de entradas invalidas."""

    def test_steps_vacios_lanzan_valueerror(self):
        """evaluate con lista vacia falla con WHAT+WHY+WHERE."""
        with pytest.raises(ValueError) as excinfo:
            TrajectoryEvaluator().evaluate("task-vacio", [])
        msg = str(excinfo.value)
        assert "WHAT" in msg
        assert "WHY" in msg
        assert "WHERE" in msg

    def test_evaluate_retorna_trajectory_report(self):
        """evaluate devuelve una instancia de TrajectoryReport."""
        report = TrajectoryEvaluator().evaluate("task-rt", [_step("builder", "write_code")])
        assert isinstance(report, TrajectoryReport)
