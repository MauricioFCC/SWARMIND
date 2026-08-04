"""
test_tdd_flow_integration.py - Prueba end-to-end del flujo ADR-0033.

Valida que las piezas del flujo TDD estricto operan juntas como un sistema:

    1. DAG TDD (Spec -> Green -> Confianza) con validacion estructural.
    2. TDDGate: las prohibiciones de oro RED/GREEN/REFACTOR bloquean violaciones.
    3. TrajectoryEvaluator: audita la trayectoria del DAG ejecutado.
    4. RedTeamer: ataca el codigo producido antes de desplegar.
    5. ContinuousVerifier: verifica post-deploy y revierte si hay degradacion.
    6. TestConfidenceReport: unica salida al humano, sin mostrar codigo.

El test simula una sesion completa de produccion: spec -> green -> confianza
-> ataque adversarial -> deploy -> verificacion de 30 minutos.
"""
from __future__ import annotations

from harness.orchestrator.continuous_verifier import ContinuousVerifier
from harness.orchestrator.red_teamer import RedTeamer
from harness.orchestrator.trajectory_evaluator import (
    TrajectoryEvaluator,
    TrajectoryReport,
    TrajectoryStep,
)
from harness.orchestrator.workflows.tdd_strict import (
    TDDGate,
    TDDPhase,
    TestConfidenceReport,
    build_tdd_dag,
)


class TestTDDFlowIntegration:
    """Prueba el flujo ADR-0033 completo como un sistema orquestado."""

    def test_dag_spec_green_confianza_structure(self) -> None:
        """El DAG tiene los 3 niveles canonicos con sus agentes y fases."""
        dag = build_tdd_dag()
        assert dag["name"] == "tdd_strict"
        assert [level["name"] for level in dag["levels"]] == [
            "Spec",
            "Green",
            "Confianza",
        ]
        assert dag["levels"][0]["phase"] == "RED"
        assert dag["levels"][1]["phase"] == "GREEN"
        assert dag["levels"][2]["phase"] is None
        assert dag["levels"][0]["agents"] == ["scientist", "guardian"]
        assert dag["levels"][1]["agents"] == ["builder", "guardian"]
        assert dag["levels"][2]["agents"] == ["coordinator"]

    def test_gate_block_violations_across_phases(self) -> None:
        """Las tres prohibiciones de oro bloquean la violacion correspondiente."""
        gate = TDDGate()
        # RED: escribir src/ esta prohibido (solo tests que fallan).
        ok, msg = gate.validate_phase(TDDPhase.RED, False, True)
        assert not ok
        assert "RED" in msg and "PROHIBIDO" in msg
        # GREEN: tocar tests esta prohibido.
        ok, msg = gate.validate_phase(TDDPhase.GREEN, True, False)
        assert not ok
        assert "GREEN" in msg and "PROHIBIDO" in msg
        # REFACTOR: cambiar tests o comportamiento esta prohibido.
        ok, msg = gate.validate_phase(TDDPhase.REFACTOR, True, False)
        assert not ok
        assert "REFACTOR" in msg and "PROHIBIDO" in msg

    def test_confidence_report_is_only_output_no_code(self) -> None:
        """El reporte de confianza no expone codigo, solo metricas agregadas."""
        report = TestConfidenceReport(
            tests_passed=142,
            tests_total=142,
            pbt_generations=5000,
            mutation_score=88.5,
            surviving_mutants=12,
            branch_coverage=96.2,
            sandbox_iterations=4,
            sandbox_duration_seconds=192.0,
            files_modified=("src/mod_a.py", "src/mod_b.py", "src/mod_c.py"),
        )
        text = report.render()
        assert "ESPECIFICACIÓN APROBADA" in text
        assert "142/142" in text
        assert "88.5" in text and "Robusto" in text
        assert "Archivos modificados: 3" in text
        # El reporte NUNCA muestra rutas ni contenido de archivos.
        assert "src/mod_a.py" not in text
        assert "mod_b" not in text

    def test_trajectory_evaluator_audits_dag_execution(self) -> None:
        """La trayectoria del DAG ejecutado se audita y detecta ineficiencias."""
        evaluator = TrajectoryEvaluator()
        report: TrajectoryReport = evaluator.evaluate(
            task_id="tdd-task-1",
            steps=[
                TrajectoryStep(agent="coordinator", action="descomponer", duration_ms=100.0),
                TrajectoryStep(agent="scientist", action="definir_tests", duration_ms=200.0),
                TrajectoryStep(agent="builder", action="implementar", duration_ms=400.0),
                TrajectoryStep(agent="builder", action="implementar", duration_ms=400.0),
                TrajectoryStep(agent="builder", action="implementar", duration_ms=400.0),
                TrajectoryStep(agent="guardian", action="mutar", duration_ms=150.0),
                TrajectoryStep(agent="coordinator", action="reportar", duration_ms=50.0),
            ],
        )
        assert report.agents_used == 4
        assert report.steps == 7
        assert report.redundancy_score > 0.0
        # Heuristica: 3 builders repetidos (3/7) penalizan ~21 puntos -> ACCEPTABLE.
        assert report.verdict == "ACCEPTABLE"
        assert any("builder" in rec for rec in report.recommendations)

    def test_trajectory_judge_flags_inefficient_overdelegation(self) -> None:
        """El LLM-as-judge puede declarar INEFFICIENT por sobre-delegacion."""
        judge = lambda prompt: (
            "VERDICTO: INEFFICIENT\n"
            "RAZON: 5 agentes para 2 pasos es sobre-delegacion evidente.\n"
        )
        evaluator = TrajectoryEvaluator(judge=judge)
        report = evaluator.evaluate(
            task_id="tdd-task-2",
            steps=[
                TrajectoryStep(agent="coordinator", action="descomponer", duration_ms=50.0),
                TrajectoryStep(agent="builder", action="implementar", duration_ms=300.0),
            ],
        )
        assert report.verdict == "INEFFICIENT"
        assert report.efficiency_score < 60.0
        assert any("5 agentes" in rec for rec in report.recommendations)

    def test_red_teamer_blocks_vulnerable_deploy(self) -> None:
        """El red-teamer bloquea el deploy si el codigo refleja ataques."""
        red_teamer = RedTeamer()

        def vulnerable_responder(payload: str) -> str:
            return f"ECHO: {payload}"

        findings, deploy_allowed = red_teamer.audit(
            target="src/codigo_producido.py", responder=vulnerable_responder
        )
        assert not deploy_allowed
        assert any(f.vulnerable for f in findings)
        assert any(f.severity == "CRITICAL" for f in findings)
        assert red_teamer.stats(findings)["CRITICAL"] >= 1

    def test_continuous_verifier_rolls_back_degradation(self) -> None:
        """El CV revierte automaticamente si la metrica degrada >5%."""
        verifier = ContinuousVerifier(degradation_threshold_pct=5.0)
        verifier.register_baseline("deploy-001", {"latency_ms": 100.0})
        verifier.record_sample("deploy-001", "latency_ms", 106.0)  # +6% > umbral.
        result = verifier.verify("deploy-001")
        assert not result.passed
        assert result.rollback_triggered
        assert "latency_ms" in result.degraded_metrics
        assert verifier.get_rollback_log()  # rollback registrado para evolve-analyzer

    def test_full_session_flow_ends_green(self) -> None:
        """Flujo completo sin vulnerabilidades: deploy aprobado y verificacion OK."""
        # 1) Spec: scientist define tests, guardian audita. Gate RED valida.
        gate = TDDGate()
        ok_spec, _ = gate.validate_phase(TDDPhase.RED, True, False)
        assert ok_spec
        # 2) Green: builder implementa, guardian muta. Gate GREEN valida.
        ok_green, _ = gate.validate_phase(TDDPhase.GREEN, False, True)
        assert ok_green
        # 3) Confianza: coordinator reporta sin codigo.
        report = TestConfidenceReport(
            tests_passed=50,
            tests_total=50,
            pbt_generations=1000,
            mutation_score=90.0,
            surviving_mutants=3,
            branch_coverage=95.0,
            sandbox_iterations=2,
        )
        assert "ESPECIFICACIÓN APROBADA" in report.render()
        # 4) Red-team: responder sano (rechaza todo) -> deploy permitido.
        red_teamer = RedTeamer()
        safe_responder = lambda payload: ""
        _, deploy_allowed = red_teamer.audit("src/feature_x.py", responder=safe_responder)
        assert deploy_allowed
        # 5) CV post-deploy: sin degradacion -> sin rollback.
        verifier = ContinuousVerifier(degradation_threshold_pct=5.0)
        verifier.register_baseline("deploy-002", {"latency_ms": 100.0})
        verifier.record_sample("deploy-002", "latency_ms", 102.0)  # +2% OK.
        result = verifier.verify("deploy-002")
        assert result.passed
        assert not result.rollback_triggered
        assert verifier.get_rollback_log() == []
