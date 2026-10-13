"""Tests TDD para ``harness.observability.harness_health`` (panel de salud).

WHAT: valida el panel unificado que agrega los TRES medidores de frontera del
harness —token telemetry (TKN), Library Drift (retiro por outcome) y
Consistency (estabilidad run-to-run)— mas el Skill Lift (skills daninas) en un
unico veredicto operativo. WHY: los medidores existian pero estaban cableados
SIN un reporte unico ni ejecucion programada; sin un veredicto agregado no hay
gate de CI que "active" la telemetria real. WHERE: consumido por
``scripts/harness_health.py`` (CLI) y el workflow ``skills-quality.yml``.

Patron TDD (RED primero): estos tests definen el contrato ANTES de la
implementacion. Deterministas y sin LLM real (NF-3).

Cobertura (segun el contrato de la tarea):
    (a) medidores inyectados sanos -> verdict "healthy".
    (b) hit_rate 0.5 (gate token falla) -> "degraded".
    (c) skills harmful >= 1 -> "unhealthy".
    (d) None-safe: sin consistency/lift los campos son None y no lanza.
    (e) report()/to_json() roundtrip en tmp_path; summary_markdown con campos.
    (f) sentinela de mutacion: invertir un umbral rompe 2 asserts.
    (g) CLI: verdict unhealthy -> exit code 1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# scripts/ esta fuera de harness/ -> lo agregamos al path de import (patron
# identico a test_validate_skills.py; SEG: nunca en index 0).
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(1, str(_SCRIPTS))

import harness_health as cli

from harness.observability.harness_health import (
    MAX_HARMFUL_SKILLS,
    MIN_CONSISTENCY_SCORE,
    MIN_TOKEN_HIT_RATE,
    HarnessHealth,
    HarnessHealthReporter,
    HealthThresholds,
)
from harness.observability.token_telemetry import TokenTelemetry

# ---------------------------------------------------------------------------
# Fakes / helpers deterministas (DI; 0 LLM, 0 red, 0 DB)
# ---------------------------------------------------------------------------

#: Reporte de drift sano: 5 skills activas, 0 retiradas, 0 en riesgo.
_HEALTHY_DRIFT_REPORT: dict[str, int] = {
    "total": 5,
    "protected": 0,
    "keep": 5,
    "retired": 0,
    "cap_exceeded": 0,
}

#: Reporte de consistencia sano (score >= MIN_CONSISTENCY_SCORE).
_HEALTHY_CONSISTENCY: dict[str, float] = {"consistency_score": 0.98}

#: Reporte de lift sano (0 skills daninas).
_HEALTHY_LIFT: dict[str, int] = {"useful": 3, "neutral": 0, "harmful": 0}


def _healthy_drift() -> MagicMock:
    """Crea un medidor de drift (mock) con reporte sano.

    Returns:
        MagicMock cuyo ``report()`` devuelve ``_HEALTHY_DRIFT_REPORT``.
    """
    drift = MagicMock()
    drift.report.return_value = dict(_HEALTHY_DRIFT_REPORT)
    return drift


def _healthy_telemetry() -> TokenTelemetry:
    """Crea una telemetria real con hit_rate 0.9 (>= umbral 0.80).

    Returns:
        ``TokenTelemetry`` con un unico registro de acierto 0.9.
    """
    telemetry = TokenTelemetry()
    telemetry.record_usage("coder", cached=90, input=10, output=1)
    return telemetry


def _low_telemetry() -> TokenTelemetry:
    """Crea una telemetria real con hit_rate 0.5 (< umbral 0.80).

    Returns:
        ``TokenTelemetry`` con un unico registro de acierto 0.5.
    """
    telemetry = TokenTelemetry()
    telemetry.record_usage("coder", cached=50, input=50, output=1)
    return telemetry


# ===========================================================================
# (a) Verdict healthy con medidores sanos
# ===========================================================================


class TestHealthyVerdict:
    """Todos los gates pasan -> "healthy"."""

    def test_medidores_sanos_dan_healthy(self) -> None:
        """(a) telemetria/drift/lift sanos + consistencia sana -> healthy."""
        reporter = HarnessHealthReporter(
            telemetry=_healthy_telemetry(),
            drift=_healthy_drift(),
            consistency=dict(_HEALTHY_CONSISTENCY),
            lift_report=dict(_HEALTHY_LIFT),
        )
        health = reporter.collect()
        assert isinstance(health, HarnessHealth)
        assert health.verdict == "healthy"
        assert health.token_gate_ok is True

    def test_verdict_method_coincide_con_collect(self) -> None:
        """verdict() y collect().verdict devuelven lo mismo (determinista)."""
        reporter = HarnessHealthReporter(
            telemetry=_healthy_telemetry(),
            drift=_healthy_drift(),
            consistency=dict(_HEALTHY_CONSISTENCY),
            lift_report=dict(_HEALTHY_LIFT),
        )
        assert reporter.verdict() == reporter.collect().verdict == "healthy"


# ===========================================================================
# (b) Un gate falla -> degraded
# ===========================================================================


class TestDegradedVerdict:
    """Falla exactamente 1 gate -> "degraded"."""

    def test_hit_rate_bajo_da_degraded(self) -> None:
        """(b) hit_rate 0.5 falla el gate token (unico) -> degraded."""
        reporter = HarnessHealthReporter(
            telemetry=_low_telemetry(),
            drift=_healthy_drift(),
            consistency=dict(_HEALTHY_CONSISTENCY),
            lift_report=dict(_HEALTHY_LIFT),
        )
        health = reporter.collect()
        assert health.token_hit_rate == pytest.approx(0.5)
        assert health.token_gate_ok is False
        assert health.verdict == "degraded"

    def test_consistencia_baja_da_degraded(self) -> None:
        """(b') consistencia por debajo del umbral (unico fallo) -> degraded."""
        reporter = HarnessHealthReporter(
            telemetry=_healthy_telemetry(),
            drift=_healthy_drift(),
            consistency={"consistency_score": 0.5},
            lift_report=dict(_HEALTHY_LIFT),
        )
        assert reporter.verdict() == "degraded"


# ===========================================================================
# (c) Skills daninas -> unhealthy
# ===========================================================================


class TestUnhealthyVerdict:
    """Skills daninas fuerzan "unhealthy" aunque los demas gates pasen."""

    def test_skill_harmful_da_unhealthy(self) -> None:
        """(c) lift harmful >= 1 -> unhealthy (aunque token/consistency OK)."""
        reporter = HarnessHealthReporter(
            telemetry=_healthy_telemetry(),
            drift=_healthy_drift(),
            consistency=dict(_HEALTHY_CONSISTENCY),
            lift_report={"useful": 0, "neutral": 0, "harmful": 1},
        )
        health = reporter.collect()
        assert health.lift_harmful == 1
        assert health.verdict == "unhealthy"

    def test_dos_gates_fallando_dan_unhealthy(self) -> None:
        """(c') token + consistency fallan (>=2 gates) -> unhealthy."""
        reporter = HarnessHealthReporter(
            telemetry=_low_telemetry(),
            drift=_healthy_drift(),
            consistency={"consistency_score": 0.1},
            lift_report=dict(_HEALTHY_LIFT),
        )
        assert reporter.verdict() == "unhealthy"


# ===========================================================================
# (d) None-safe (medidores ausentes)
# ===========================================================================


class TestNoneSafe:
    """Sin consistency/lift inyectados los campos son None y no lanza."""

    def test_sin_consistency_ni_lift_no_lanza(self) -> None:
        """(d) telemetria+drift sanos, sin consistency/lift -> healthy."""
        reporter = HarnessHealthReporter(
            telemetry=_healthy_telemetry(),
            drift=_healthy_drift(),
        )
        health = reporter.collect()
        assert health.consistency_score is None
        assert health.lift_harmful is None
        assert health.verdict == "healthy"

    def test_sin_ningun_medidor_no_lanza(self) -> None:
        """(d') reporter sin medidores: no lanza; campos None; no healthy."""
        reporter = HarnessHealthReporter()
        health = reporter.collect()
        assert health.consistency_score is None
        assert health.lift_harmful is None
        assert health.skills_total == 0
        assert health.verdict in {"degraded", "unhealthy"}


# ===========================================================================
# (e) report() / to_json() / summary_markdown()
# ===========================================================================


class TestReportAndPersistence:
    """report() y to_json() hacen roundtrip; summary_markdown lista campos."""

    def _reporter(self) -> HarnessHealthReporter:
        """Reporter completo y sano para los tests de reporte."""
        return HarnessHealthReporter(
            telemetry=_healthy_telemetry(),
            drift=_healthy_drift(),
            consistency=dict(_HEALTHY_CONSISTENCY),
            lift_report=dict(_HEALTHY_LIFT),
        )

    def test_report_incluye_thresholds_y_health(self) -> None:
        """report() expone los campos de salud y los umbrales aplicados."""
        payload = self._reporter().report()
        assert payload["verdict"] == "healthy"
        assert payload["token_hit_rate"] == pytest.approx(0.9)
        assert payload["thresholds"]["min_token_hit_rate"] == MIN_TOKEN_HIT_RATE
        assert payload["thresholds"]["max_harmful_skills"] == MAX_HARMFUL_SKILLS
        assert payload["thresholds"]["min_consistency_score"] == MIN_CONSISTENCY_SCORE

    def test_to_json_roundtrip(self, tmp_path: Path) -> None:
        """(e) to_json escribe JSON parseable y conserva los campos clave."""
        reporter = self._reporter()
        health = reporter.collect()
        path = tmp_path / "harness_health.json"

        assert reporter.to_json(path) is True
        loaded = json.loads(path.read_text(encoding="utf-8"))

        assert loaded["verdict"] == health.verdict
        assert loaded["token_hit_rate"] == pytest.approx(health.token_hit_rate)
        assert loaded["skills_total"] == health.skills_total
        assert loaded["consistency_score"] == health.consistency_score

    def test_to_json_oserror_es_best_effort(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """to_json ante OSError -> False + warning (0 except silenciosos)."""
        reporter = self._reporter()
        # Un archivo (no dir) como padre invalida la creacion del directorio:
        # mkdir lanza FileExistsError, que ES un OSError (portable a Windows).
        blocker = tmp_path / "blocker"
        blocker.write_text("no soy un directorio", encoding="utf-8")
        bad_path = blocker / "no_puede.json"
        with caplog.at_level("WARNING"):
            result = reporter.to_json(bad_path)
        assert result is False
        assert any(record.levelname == "WARNING" for record in caplog.records)

    def test_summary_markdown_contiene_campos(self) -> None:
        """(e) summary_markdown incluye todos los campos del panel."""
        markdown = self._reporter().summary_markdown()
        for field in (
            "token_hit_rate",
            "token_gate_ok",
            "skills_total",
            "skills_retired",
            "skills_at_risk",
            "consistency_score",
            "lift_harmful",
            "generated_at",
            "verdict",
        ):
            assert field in markdown
        assert "healthy" in markdown


# ===========================================================================
# (f) Sentinela de mutacion: umbrales en el limite
# ===========================================================================


class TestThresholdMutation:
    """Los gates son inclusivos en el limite; invertir el comparador rompe."""

    def test_gate_token_inclusivo_en_el_limite(self) -> None:
        """(f) hit_rate == umbral pasa el gate (mutar >= a > lo rompe)."""
        telemetry = TokenTelemetry()
        telemetry.record_usage("coder", cached=90, input=10, output=1)  # exacto 0.9
        thresholds = HealthThresholds(min_token_hit_rate=0.9)
        health = HarnessHealthReporter(telemetry=telemetry, thresholds=thresholds).collect()
        assert health.token_gate_ok is True  # mutacion >= -> > rompe este assert
        assert health.verdict == "healthy"  # ...y este tambien (2 asserts)

    def test_gate_consistencia_inclusivo_en_el_limite(self) -> None:
        """(f') score == umbral pasa el gate (mutar >= a > lo rompe)."""
        thresholds = HealthThresholds(min_consistency_score=0.9)
        reporter = HarnessHealthReporter(
            telemetry=_healthy_telemetry(),
            consistency={"consistency_score": 0.9},
            thresholds=thresholds,
        )
        health = reporter.collect()
        assert health.consistency_score == pytest.approx(0.9)  # mutacion rompe
        assert health.verdict == "healthy"  # mutacion rompe (2 asserts)


# ===========================================================================
# HealthThresholds.from_env()
# ===========================================================================


class TestThresholdsFromEnv:
    """HealthThresholds.from_env() lee los overrides del entorno."""

    def test_defaults_sin_entorno(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sin variables de entorno usa los umbrales por defecto."""
        for name in (
            "SWARMIND_HEALTH_MIN_TOKEN_HIT_RATE",
            "SWARMIND_HEALTH_MAX_HARMFUL_SKILLS",
            "SWARMIND_HEALTH_MIN_CONSISTENCY_SCORE",
        ):
            monkeypatch.delenv(name, raising=False)
        thresholds = HealthThresholds.from_env()
        assert thresholds.min_token_hit_rate == MIN_TOKEN_HIT_RATE
        assert thresholds.max_harmful_skills == MAX_HARMFUL_SKILLS
        assert thresholds.min_consistency_score == MIN_CONSISTENCY_SCORE

    def test_lee_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lee y parsea los overrides del entorno."""
        monkeypatch.setenv("SWARMIND_HEALTH_MIN_TOKEN_HIT_RATE", "0.5")
        monkeypatch.setenv("SWARMIND_HEALTH_MAX_HARMFUL_SKILLS", "2")
        monkeypatch.setenv("SWARMIND_HEALTH_MIN_CONSISTENCY_SCORE", "0.75")
        thresholds = HealthThresholds.from_env()
        assert thresholds.min_token_hit_rate == pytest.approx(0.5)
        assert thresholds.max_harmful_skills == 2
        assert thresholds.min_consistency_score == pytest.approx(0.75)

    def test_valor_invalido_usa_default(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Un valor no parseable cae al default con warning (best-effort)."""
        monkeypatch.setenv("SWARMIND_HEALTH_MIN_TOKEN_HIT_RATE", "no-numero")
        with caplog.at_level("WARNING"):
            thresholds = HealthThresholds.from_env()
        assert thresholds.min_token_hit_rate == MIN_TOKEN_HIT_RATE
        assert any(record.levelname == "WARNING" for record in caplog.records)


# ===========================================================================
# (g) CLI: exit code
# ===========================================================================


class TestCliExitCode:
    """El CLI devuelve 0 (healthy/degraded) y 1 (unhealthy) para CI."""

    def test_unhealthy_devuelve_exit_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """(g) telemetria ruin + consistencia flaky -> unhealthy -> exit 1."""
        telemetry_path = tmp_path / "telemetry.json"
        telemetry_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "records": [
                        {
                            "role": "coder",
                            "cached_tokens": 0,
                            "input_tokens": 100,
                            "output_tokens": 0,
                            "timestamp": "2026-10-13T00:00:00+00:00",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        code = cli.main(
            [
                "--telemetry",
                str(telemetry_path),
                "--drift-path",
                str(tmp_path / "skill_utility.jsonl"),
                "--consistency-tasks",
                "flaky-demo",
                "--runs",
                "2",
                "--json",
            ]
        )
        assert code == 1

    def test_degraded_devuelve_exit_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Sin telemetria (hit_rate 0) pero resto sano -> degraded -> exit 0."""
        code = cli.main(
            [
                "--telemetry",
                str(tmp_path / "ausente.json"),
                "--drift-path",
                str(tmp_path / "skill_utility.jsonl"),
                "--json",
            ]
        )
        assert code == 0
