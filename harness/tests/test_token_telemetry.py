"""Tests TDD para TokenTelemetry — telemetria de tokens/cache (FR-A1, ADR-0103).

Cubre el workstream WS-A (token economics): registro thread-safe por rol,
``hit_rate`` exacto, ``gate_ok``, ``report`` resumido y persistencia JSON.
Determinista y sin LLM real (NF-3).

Patron TDD (RED primero): estos tests definen el contrato ANTES de la
implementacion en ``harness/observability/token_telemetry.py``.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from harness.observability.token_telemetry import (
    TokenTelemetry,
    UsageRecord,
)

# ===========================================================================
# UsageRecord
# ===========================================================================


class TestUsageRecord:
    """Contrato del registro inmutable de uso (IMM: frozen dataclass)."""

    def test_is_frozen(self) -> None:
        """UsageRecord: inmutable (frozen) — mutar lanza FrozenInstanceError."""
        record = UsageRecord(
            role="coder",
            cached_tokens=1,
            input_tokens=2,
            output_tokens=3,
            timestamp="2026-10-12T00:00:00+00:00",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            record.role = "otro"  # type: ignore[misc]


# ===========================================================================
# Acumulacion
# ===========================================================================


class TestAccumulation:
    """record_usage acumula por rol y totales."""

    def test_accumulates_by_role_and_total(self) -> None:
        """record_usage: suma por rol y agrega totales correctamente."""
        telemetry = TokenTelemetry()
        telemetry.record_usage("coder", cached=100, input=400, output=50)
        telemetry.record_usage("coder", cached=50, input=200, output=25)
        telemetry.record_usage("reviewer", cached=10, input=90, output=5)

        report = telemetry.report()
        assert report["roles"]["coder"]["cached_tokens"] == 150
        assert report["roles"]["coder"]["input_tokens"] == 600
        assert report["roles"]["coder"]["output_tokens"] == 75
        assert report["roles"]["coder"]["records"] == 2
        assert report["roles"]["reviewer"]["records"] == 1

        assert report["total"]["cached_tokens"] == 160
        assert report["total"]["input_tokens"] == 690
        assert report["total"]["output_tokens"] == 80
        assert report["total"]["records"] == 3

    def test_rejects_negative_values(self) -> None:
        """record_usage: valores negativos → ValueError (VAL/FST)."""
        telemetry = TokenTelemetry()
        with pytest.raises(ValueError):
            telemetry.record_usage("coder", cached=-1, input=10, output=0)

    def test_rejects_empty_role(self) -> None:
        """record_usage: rol vacio → ValueError (contrato de API)."""
        telemetry = TokenTelemetry()
        with pytest.raises(ValueError):
            telemetry.record_usage("   ", cached=1, input=1, output=1)


# ===========================================================================
# hit_rate
# ===========================================================================


class TestHitRate:
    """hit_rate() = cached / (input + cached)."""

    def test_exact_value(self) -> None:
        """hit_rate: 90/(10+90) == 0.9 exacto."""
        telemetry = TokenTelemetry()
        telemetry.record_usage("coder", cached=90, input=10, output=5)
        assert telemetry.hit_rate() == pytest.approx(0.9)

    def test_zero_when_empty(self) -> None:
        """hit_rate: sin registros → 0.0 (denominador cero)."""
        assert TokenTelemetry().hit_rate() == 0.0

    def test_zero_when_denominator_zero(self) -> None:
        """hit_rate: solo output (denominador 0) → 0.0."""
        telemetry = TokenTelemetry()
        telemetry.record_usage("coder", cached=0, input=0, output=42)
        assert telemetry.hit_rate() == 0.0


# ===========================================================================
# gate_ok
# ===========================================================================


class TestGateOk:
    """gate_ok(threshold) evalua el umbral de cache-hit."""

    def test_true_above_threshold(self) -> None:
        """gate_ok: hit_rate 0.9 >= 0.80 → True."""
        telemetry = TokenTelemetry()
        telemetry.record_usage("coder", cached=900, input=100, output=10)
        assert telemetry.gate_ok(threshold=0.80) is True

    def test_false_below_threshold(self) -> None:
        """gate_ok: hit_rate 0.5 < 0.80 → False."""
        telemetry = TokenTelemetry()
        telemetry.record_usage("coder", cached=50, input=50, output=10)
        assert telemetry.gate_ok(threshold=0.80) is False

    def test_boundary_inclusive(self) -> None:
        """gate_ok: exactamente en el umbral (0.80) → True."""
        telemetry = TokenTelemetry()
        telemetry.record_usage("coder", cached=80, input=20, output=1)
        assert telemetry.gate_ok(threshold=0.80) is True


# ===========================================================================
# report
# ===========================================================================


class TestReport:
    """report() resume por rol + total + hit_rate."""

    def test_empty_report(self) -> None:
        """report: telemetria vacia → roles vacio, total 0, hit_rate 0.0."""
        report = TokenTelemetry().report()
        assert report["roles"] == {}
        assert report["total"]["records"] == 0
        assert report["hit_rate"] == 0.0

    def test_includes_roles_hit_rate_and_total(self) -> None:
        """report: incluye desglose por rol, total y hit_rate."""
        telemetry = TokenTelemetry()
        telemetry.record_usage("coder", cached=75, input=25, output=1)
        report = telemetry.report()
        assert "coder" in report["roles"]
        assert report["hit_rate"] == pytest.approx(0.75)
        assert report["total"]["cached_tokens"] == 75


# ===========================================================================
# Thread safety
# ===========================================================================


class TestThreadSafety:
    """10 hilos x 100 registros no pierden conteo (Lock)."""

    def test_concurrent_records_no_loss(self) -> None:
        """Concurrencia: 1000 registros exactos sin perdidas."""
        import threading

        telemetry = TokenTelemetry()
        threads = 10
        per_thread = 100

        def worker() -> None:
            for _ in range(per_thread):
                telemetry.record_usage("coder", cached=1, input=1, output=1)

        pool = [threading.Thread(target=worker) for _ in range(threads)]
        for thread in pool:
            thread.start()
        for thread in pool:
            thread.join()

        report = telemetry.report()
        assert report["total"]["records"] == threads * per_thread
        assert report["roles"]["coder"]["records"] == threads * per_thread
        assert report["total"]["cached_tokens"] == threads * per_thread


# ===========================================================================
# Persistencia
# ===========================================================================


class TestPersistence:
    """to_json/from_json roundtrip y manejo best-effort de OSError."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        """to_json + from_json: conserva el reporte agregado."""
        telemetry = TokenTelemetry()
        telemetry.record_usage("coder", cached=100, input=400, output=50)
        telemetry.record_usage("reviewer", cached=10, input=90, output=5)

        path = tmp_path / "telemetry.json"
        assert telemetry.to_json(path) is True
        assert path.exists()

        restored = TokenTelemetry.from_json(path)
        assert restored is not None
        assert restored.report() == telemetry.report()

    def test_to_json_oserror_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """to_json: OSError → warning, retorna False (0 except silenciosos)."""
        telemetry = TokenTelemetry()
        telemetry.record_usage("coder", cached=1, input=1, output=1)
        bad_path = tmp_path / "no_existe" / "telemetry.json"
        with caplog.at_level("WARNING"):
            assert telemetry.to_json(bad_path) is False
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_from_json_missing_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """from_json: archivo inexistente → None + warning (best-effort)."""
        with caplog.at_level("WARNING"):
            assert TokenTelemetry.from_json(tmp_path / "missing.json") is None
        assert any(r.levelname == "WARNING" for r in caplog.records)
