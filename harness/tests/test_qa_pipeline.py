"""Tests para el pipeline de QA 5-capas — API real de las implementaciones.

Adaptado a las firmas reales de los modulos generados.
"""

from __future__ import annotations

import pytest

from harness.qa.agent import AgentResult, AutonomousTestAgent
from harness.qa.detector import (
    AnomalyFinding,
    AnomalyReport,
    AnomalyType,
    VisualAnomalyDetector,
)
from harness.qa.generator import TestCaseGenerator, TestSuite
from harness.qa.orchestrator import (
    OrchestrationReport,
    PipelineStatus,
    QAOrchestrator,
)
from harness.qa.predictor import FailurePredictor, HistorialEjecucion, RiskScore

# ============================================================================
# Tests: L1 — FailurePredictor
# ============================================================================

class TestL1FailurePredictor:
    """Tests L1: prediccion de fallos con datos normalizados [0,1]."""

    def setup_method(self) -> None:
        self.p = FailurePredictor()

    def test_predict_returns_risk_score(self) -> None:
        """predict debe retornar RiskScore valido."""
        risk = self.p.predict(target="modulo.py", complexity=0.5, churn=0.3, coverage=0.75)
        assert isinstance(risk, RiskScore)
        assert 0.0 <= risk.probability <= 1.0
        assert risk.target == "modulo.py"

    def test_low_risk_with_high_coverage(self) -> None:
        """Alta cobertura + baja complejidad = riesgo bajo."""
        risk = self.p.predict(target="simple.py", complexity=0.1, churn=0.05, coverage=0.95)
        assert risk.probability < 0.5
        assert risk.nivel in ("BAJO", "MEDIO")

    def test_high_risk_with_low_coverage(self) -> None:
        """Baja cobertura + alta complejidad = riesgo alto."""
        risk = self.p.predict(target="complejo.py", complexity=0.9, churn=0.8, coverage=0.2)
        assert risk.probability > 0.3

    def test_historial_ejecucion(self) -> None:
        """Registrar historial y predecir con el."""
        hist = HistorialEjecucion(test_id="test_login", total_runs=10, failures=3, avg_duration_ms=200.0)
        self.p.registrar_historial(hist)
        risk = self.p.predict(target="test_login", complexity=0.3, churn=0.1, coverage=0.9)
        assert risk.probability > 0

    def test_historial_invalid(self) -> None:
        """Valida que failures <= total_runs."""
        with pytest.raises(ValueError):
            HistorialEjecucion(test_id="bad", total_runs=5, failures=10, avg_duration_ms=1.0)

    def test_risk_score_nivel_labels(self) -> None:
        """RiskScore.nivel debe clasificar correctamente."""
        assert RiskScore(target="x", probability=0.1).nivel == "BAJO"
        assert RiskScore(target="x", probability=0.5).nivel == "MEDIO"
        assert RiskScore(target="x", probability=0.85).nivel == "ALTO"


# ============================================================================
# Tests: L2 — VisualAnomalyDetector
# ============================================================================

class TestL2VisualAnomalyDetector:
    """Tests L2: deteccion de anomalias con dict[str, float]."""

    def setup_method(self) -> None:
        self.d = VisualAnomalyDetector()

    def test_scan_no_anomalies(self) -> None:
        """Datos uniformes sin anomalias."""
        report = self.d.scan({f"t{i}": 1.0 for i in range(10)})
        assert isinstance(report, AnomalyReport)

    def test_scan_detects_outliers(self) -> None:
        """Valor extremo debe detectarse como anomalia."""
        data = {f"t{i}": float(i) for i in range(5)}
        data["outlier"] = 100.0
        report = self.d.scan(data)
        assert len(report.anomalies) > 0

    def test_scan_minimal_data(self) -> None:
        """Dataset minimo debe funcionar."""
        report = self.d.scan({"a": 1.0, "b": 2.0})
        assert isinstance(report, AnomalyReport)

    def test_anomaly_finding_creation(self) -> None:
        """Creacion de AnomalyFinding con campos reales."""
        finding = AnomalyFinding(
            tipo=AnomalyType.DURATION_SPIKE,
            severidad=0.8,
            descripcion="Pico de duracion detectado",
            ubicacion="test_login",
            valor_observado=5000.0,
            valor_esperado=100.0,
        )
        assert finding.valor_observado == 5000.0
        assert finding.tipo == AnomalyType.DURATION_SPIKE


# ============================================================================
# Tests: L3 — TestCaseGenerator
# ============================================================================

class TestL3TestCaseGenerator:
    """Tests L3: generacion de casos con guardrails."""

    def setup_method(self) -> None:
        self.g = TestCaseGenerator()

    def test_generate_returns_suite(self) -> None:
        """generate debe retornar TestSuite."""
        suite = self.g.generate(especificacion="Funcion validar_email")
        assert isinstance(suite, TestSuite)


# ============================================================================
# Tests: L4 — AutonomousTestAgent
# ============================================================================

class TestL4AutonomousTestAgent:
    """Tests L4: ejecucion autonoma."""

    def setup_method(self) -> None:
        self.a = AutonomousTestAgent()

    def test_run_returns_result(self) -> None:
        """run debe retornar AgentResult."""
        result = self.a.run(test_files=["tests/test_auth.py"])
        assert isinstance(result, AgentResult)
        assert result.total > 0


# ============================================================================
# Tests: L5 — QAOrchestrator
# ============================================================================

class TestL5QAOrchestrator:
    """Tests L5: orquestacion completa."""

    def setup_method(self) -> None:
        self.o = QAOrchestrator()

    def test_execute_returns_report(self) -> None:
        """execute debe retornar OrchestrationReport."""
        report = self.o.execute(
            componente="auth-service",
            test_files=["tests/test_auth.py"],
            especificacion="Autenticacion JWT",
        )
        assert isinstance(report, OrchestrationReport)
        assert report.estado in (PipelineStatus.SUCCESS, PipelineStatus.DEGRADED, PipelineStatus.COMPENSATED)

    def test_calidad_global_range(self) -> None:
        """calidad_global entre 0 y 1."""
        report = self.o.execute(componente="test", test_files=[], especificacion="test")
        assert 0.0 <= report.calidad_global <= 1.0

    def test_execute_sin_tests(self) -> None:
        """Sin test files debe funcionar con estado COMPENSATED o DEGRADED."""
        report = self.o.execute(componente="nuevo", test_files=[], especificacion="nuevo componente")
        assert report.estado in (PipelineStatus.SUCCESS, PipelineStatus.DEGRADED, PipelineStatus.COMPENSATED)
