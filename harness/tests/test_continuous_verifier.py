"""Tests para ContinuousVerifier — Continuous Verification (CV) post-deploy.

Cubre ADR-0033 y el plan maestro (Fase 3.3): monitoriza metricas de negocio
post-despliegue; si una metrica sube mas del umbral respecto al baseline, se
revierte el cambio automaticamente y se registra el rollback.
"""
from __future__ import annotations

import logging

import pytest

from harness.orchestrator.continuous_verifier import (
    ContinuousVerifier,
    MetricSample,
    VerificationResult,
)


class FakeClock:
    """Reloj inyectable para controlar el tiempo en los tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    """FakeClock compartido por los tests sensibles al tiempo."""
    return FakeClock()


def _make_verifier(clock: FakeClock | None = None) -> ContinuousVerifier:
    """Crea un ContinuousVerifier con clock opcional inyectado."""
    return ContinuousVerifier(clock=clock)


class TestContinuousVerifier:
    """Verificacion continua post-deploy con baseline y muestras."""

    def test_healthy_metrics_pass_without_rollback(self, clock: FakeClock) -> None:
        """Baseline + muestras que suben 2% -> passed, sin rollback."""
        verifier = _make_verifier(clock)
        verifier.register_baseline("dep-1", {"latency_ms": 100.0, "error_rate": 1.0})
        verifier.record_sample("dep-1", "latency_ms", 102.0)
        verifier.record_sample("dep-1", "error_rate", 1.01)

        result = verifier.verify("dep-1")

        assert result.passed is True
        assert result.rollback_triggered is False
        assert result.degraded_metrics == []
        assert verifier.get_rollback_log() == []

    def test_metric_rising_6_percent_triggers_rollback(self, clock: FakeClock) -> None:
        """Baseline + muestra que sube 6% -> degradado y rollback automatico."""
        verifier = _make_verifier(clock)
        verifier.register_baseline("dep-2", {"latency_ms": 100.0})
        verifier.record_sample("dep-2", "latency_ms", 106.0)

        result = verifier.verify("dep-2")

        assert result.passed is False
        assert result.rollback_triggered is True
        assert "latency_ms" in result.degraded_metrics
        # ADR-0033: el verifier ejecuta rollback automatico al commit anterior.
        assert len(verifier.get_rollback_log()) == 1

    def test_exact_threshold_is_not_degraded(self, clock: FakeClock) -> None:
        """Degradacion exactamente al umbral (5.0%) NO es degradacion."""
        verifier = _make_verifier(clock)
        verifier.register_baseline("dep-3", {"latency_ms": 100.0})
        verifier.record_sample("dep-3", "latency_ms", 105.0)

        result = verifier.verify("dep-3")

        assert result.passed is True
        assert result.degraded_metrics == []
        assert result.rollback_triggered is False

    def test_rollback_message_and_log(self, clock: FakeClock) -> None:
        """rollback() genera mensaje con deployment_id y reason, y queda en log."""
        verifier = _make_verifier(clock)

        message = verifier.rollback("dep-4", "latencia subio 8%")

        assert message == "ROLLBACK: dep-4 — latencia subio 8%"
        log = verifier.get_rollback_log()
        assert len(log) == 1
        entry = log[0]
        assert entry["deployment_id"] == "dep-4"
        assert entry["reason"] == "latencia subio 8%"
        assert entry["timestamp"] == clock.now
        assert entry["message"] == message

    def test_check_window_active_inside_30_minutes(self, clock: FakeClock) -> None:
        """Ventana activa si el despliegue tiene menos de 30 minutos."""
        verifier = _make_verifier(clock)
        verifier.register_baseline("dep-5", {"latency_ms": 100.0})
        verifier.record_sample("dep-5", "latency_ms", 101.0)
        verifier.record_sample("dep-5", "latency_ms", 102.0)

        active, samples = verifier.check_window("dep-5")

        assert active is True
        assert samples == {"latency_ms": [101.0, 102.0]}

    def test_check_window_inactive_after_30_minutes(self, clock: FakeClock) -> None:
        """Ventana inactiva cuando pasan mas de 30 minutos del baseline."""
        verifier = _make_verifier(clock)
        verifier.register_baseline("dep-6", {"latency_ms": 100.0})
        clock.advance(30 * 60 + 1)

        active, samples = verifier.check_window("dep-6")

        assert active is False
        assert samples == {"latency_ms": []}

    def test_verify_without_baseline_raises_value_error(self) -> None:
        """verify() sin baseline registrado lanza ValueError WHAT+WHY+WHERE."""
        verifier = _make_verifier()

        with pytest.raises(ValueError, match=r"WHAT.*WHY.*WHERE"):
            verifier.verify("dep-desconocido")

    def test_stats_counts_verifications_and_rollbacks(self, clock: FakeClock) -> None:
        """stats() cuenta despliegues verificados, rollbacks y metricas degradadas."""
        verifier = _make_verifier(clock)
        verifier.register_baseline("dep-a", {"conversion": 10.0})
        verifier.register_baseline("dep-b", {"conversion": 10.0})
        verifier.verify("dep-a")
        verifier.record_sample("dep-b", "conversion", 11.0)
        verifier.verify("dep-b")

        stats = verifier.stats()

        assert stats["verified_deployments"] == 2
        assert stats["rollbacks"] == 1
        assert stats["degraded_metrics"] == 1

    def test_verify_with_explicit_current_dict(self, clock: FakeClock) -> None:
        """verify() acepta un dict actual explicito en lugar de muestras."""
        verifier = _make_verifier(clock)
        verifier.register_baseline("dep-8", {"conversion_rate": 10.0})

        healthy = verifier.verify("dep-8", current={"conversion_rate": 10.2})
        assert healthy.passed is True

        degraded = verifier.verify("dep-8", current={"conversion_rate": 10.7})
        assert degraded.passed is False
        assert "conversion_rate" in degraded.degraded_metrics

    def test_zero_baseline_avoids_division_by_zero(
        self, clock: FakeClock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Baseline 0 no divide por cero: no degradada y log WHAT+WHY+WHERE."""
        verifier = _make_verifier(clock)
        verifier.register_baseline("dep-9", {"error_rate": 0.0})
        verifier.record_sample("dep-9", "error_rate", 1.0)

        result = verifier.verify("dep-9")

        assert result.passed is True
        assert result.degraded_metrics == []
        warnings = [
            r for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert any("WHAT" in r.message for r in warnings)
        assert any("WHY" in r.message for r in warnings)
        assert any("WHERE" in r.message for r in warnings)

    def test_to_dict_serializable(self) -> None:
        """MetricSample y VerificationResult se serializan a dict."""
        sample = MetricSample(metric="latency_ms", value=102.5, timestamp=1000.0)
        assert sample.to_dict() == {
            "metric": "latency_ms",
            "value": 102.5,
            "timestamp": 1000.0,
        }

        result = VerificationResult(
            deployment_id="dep-10",
            passed=False,
            degraded_metrics=["latency_ms"],
            rollback_triggered=True,
            details={"compared_via": "samples"},
        )
        serialized = result.to_dict()
        assert serialized["deployment_id"] == "dep-10"
        assert serialized["passed"] is False
        assert serialized["degraded_metrics"] == ["latency_ms"]
        assert serialized["rollback_triggered"] is True
        assert serialized["details"] == {"compared_via": "samples"}

    def test_missing_metric_data_is_skipped(self, clock: FakeClock) -> None:
        """Metrica sin muestra ni valor actual no se evalua ni rompe verify()."""
        verifier = _make_verifier(clock)
        verifier.register_baseline("dep-11", {"latency_ms": 100.0, "cpu_pct": 50.0})
        verifier.record_sample("dep-11", "latency_ms", 101.0)

        result = verifier.verify("dep-11")

        assert result.passed is True
        assert result.degraded_metrics == []
        assert "cpu_pct" not in result.details["metrics"]

    def test_invalid_threshold_rejected(self) -> None:
        """Umbral no positivo se rechaza con ValueError WHAT+WHY+WHERE."""
        with pytest.raises(ValueError, match=r"WHAT.*WHY.*WHERE"):
            ContinuousVerifier(degradation_threshold_pct=0.0)

    def test_public_api_exports_three_classes(self) -> None:
        """__all__ expone MetricSample, VerificationResult y ContinuousVerifier."""
        import harness.orchestrator.continuous_verifier as cv

        assert set(cv.__all__) == {
            "MetricSample",
            "VerificationResult",
            "ContinuousVerifier",
        }
