"""Contrato de graduacion de evals capability->regression (spec frontera 11.15).

WHAT: verifica ``RegressionTracker`` contra la guia frontera de Anthropic
("Demystifying evals for AI agents", 2026-01):

1. Las suites de REGRESION deben tener pass-rate ~100%; una caida senala
   breakage y debe alertar comparando contra la baseline historica
   (``is_regression`` con ``dropped`` de tareas concretas).
2. Un pass-rate de 100% satura la senal ("Eval saturation"): el reporte lo
   marca (``saturated``) para que la suite se endurezca o gradue.
3. Historial APPEND-ONLY (JSONL): las corridas previas jamas se reescriben
   (recovery determinism + auditoria).
4. La baseline es la media por tarea de las corridas PREVIAS (sin incluir la
   actual, que no sesga su propia comparacion).
5. Input validado: scores fuera de [0, 1] se rechazan (WHAT+WHY+WHERE).

WHY: sin regression tracking, un refactor que degrada al 80% pasa inadvertido
mientras la suite "exista"; sin saturacion, un 100% no estimula mejorar.

WHERE: ``harness/evals/regression_tracker.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.evals.regression_tracker import (
    MAX_DROP_PP,
    MIN_REGRESSION_PASS_RATE,
    RegressionTracker,
)

#: Corrida perfecta de referencia (todas las tareas OK).
_PERFECT = {"task-a": 1.0, "task-b": 1.0, "task-c": 1.0}


def _tracker(tmp_path: Path) -> RegressionTracker:
    """Tracker con historial JSONL en ``tmp_path``."""
    return RegressionTracker(tmp_path / "history.jsonl")


def test_reporte_inicial_sin_baseline(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)

    report = tracker.evaluate_and_record("swe", {"task-a": 0.8})

    assert report.baseline_pass_rate is None, "sin historial no hay baseline"
    assert report.is_regression is False, "no hay nada de lo que regresar"
    assert report.below_bar is True, "0.8 < 0.99: la suite aun no es de regresion"
    assert report.saturated is False


def test_alerta_por_caida_vs_baseline(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    tracker.evaluate_and_record("swe", dict(_PERFECT))
    tracker.evaluate_and_record("swe", dict(_PERFECT))

    report = tracker.evaluate_and_record(
        "swe", {"task-a": 1.0, "task-b": 0.0, "task-c": 1.0}
    )

    assert report.is_regression is True, "caida de 100% a 66% = breakage"
    assert report.dropped == ("task-b",), "el reporte nombra la tarea que cayo"
    assert report.baseline_pass_rate == pytest.approx(1.0)


def test_caida_minima_no_alerta(tmp_path: Path) -> None:
    """Una caida dentro de ``MAX_DROP_PP`` NO es regression (ruido permitido)."""
    tracker = _tracker(tmp_path)
    baseline_scores = {"task-a": 1.0, "task-b": 1.0, "task-c": 1.0}
    tracker.evaluate_and_record("swe", dict(baseline_scores))
    # Caida de task-c: 1.0 -> 0.995 = 0.17pp < MAX_DROP_PP (1.0).
    report = tracker.evaluate_and_record(
        "swe", {"task-a": 1.0, "task-b": 1.0, "task-c": 0.995}
    )

    assert report.is_regression is False, (
        f"drop 0.17pp <= MAX_DROP_PP={MAX_DROP_PP}: es ruido, no breakage"
    )


def test_saturacion_marcada(tmp_path: Path) -> None:
    """100% = senal saturada: trackea regresiones pero no estimula mejorar."""
    tracker = _tracker(tmp_path)

    report = tracker.evaluate_and_record("swe", dict(_PERFECT))

    assert report.saturated is True
    assert report.is_regression is False
    assert report.below_bar is False


def test_baseline_es_media_de_corridas_previas(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    tracker.evaluate_and_record("swe", {"task-a": 1.0})
    tracker.evaluate_and_record("swe", {"task-a": 0.8})

    report = tracker.evaluate_and_record("swe", {"task-a": 0.9})

    assert report.baseline_pass_rate == pytest.approx(0.9), "media(1.0, 0.8)"


def test_historial_append_only(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    tracker.evaluate_and_record("swe", {"task-a": 1.0})
    history_file = tmp_path / "history.jsonl"
    prefix = history_file.read_bytes()

    tracker.evaluate_and_record("swe", {"task-a": 0.5})
    tracker.evaluate_and_record("swe", {"task-a": 0.2})

    after = history_file.read_bytes()
    assert after.startswith(prefix), "las corridas previas jamas se reescriben"
    assert len(after.splitlines()) == 3


def test_crea_el_directorio_del_historial(tmp_path: Path) -> None:
    """Ruta anidada inexistente: el tracker crea el arbol (mkdir parents)."""
    tracker = RegressionTracker(tmp_path / "nuevo" / "anidado" / "history.jsonl")

    report = tracker.evaluate_and_record("swe", {"task-a": 1.0})

    assert report.saturated is True
    assert (tmp_path / "nuevo" / "anidado" / "history.jsonl").is_file(), (
        "sin mkdir(parents=True) una ruta nueva explota en FileNotFoundError"
    )


def test_scores_fuera_de_rango_se_rechazan(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)

    with pytest.raises(ValueError, match="score"):
        tracker.evaluate_and_record("swe", {"task-a": 1.5})

    with pytest.raises(ValueError, match="score"):
        tracker.evaluate_and_record("swe", {"task-a": -0.1})


def test_suites_independientes(tmp_path: Path) -> None:
    """El historial de un suite no contamina la baseline de otro."""
    tracker = _tracker(tmp_path)
    tracker.evaluate_and_record("rag", {"task-a": 0.0})

    report = tracker.evaluate_and_record("swe", {"task-a": 1.0})

    assert report.baseline_pass_rate is None, "swe no hereda historial de rag"
    assert report.is_regression is False


def test_min_pass_rate_es_99_por_ciento() -> None:
    """El umbral de regresion es el canon frontera (~100% pass-rate)."""
    assert MIN_REGRESSION_PASS_RATE == 0.99
