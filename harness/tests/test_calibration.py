"""Tests para calibration — calibracion probabilistica (Brier, ECE, MCE)."""

from __future__ import annotations

import pytest

from harness.evals.calibration import (
    BIN_STRATEGY_EQUAL_MASS,
    BIN_STRATEGY_EQUAL_WIDTH,
    DEFAULT_BINS,
    MIN_POINTS,
    PERFECT_TOLERANCE,
    calibrate,
    is_well_calibrated,
)


class TestCalibratePerfecto:
    def test_forecast_perfecto_brier_y_ece_casi_cero(self):
        """p=1/y=1 y p=0/y=0 deben dar Brier~0, ECE~0 y buena calibracion."""
        outcomes = [(1.0, True)] * 5 + [(0.0, False)] * 5

        report = calibrate(outcomes)

        assert report.brier <= PERFECT_TOLERANCE
        assert report.ece <= PERFECT_TOLERANCE
        assert report.mce <= PERFECT_TOLERANCE
        assert is_well_calibrated(report) is True

    def test_hit_rate_correcto(self):
        """hit_rate debe ser la media exacta de los aciertos."""
        outcomes = [(0.8, True), (0.7, True), (0.6, False), (0.5, True), (0.4, False)]

        report = calibrate(outcomes)

        assert report.hit_rate == pytest.approx(3 / 5)

    def test_deciles_ordenados_y_suman_n(self):
        """Los bins deben ser DEFAULT_BINS y sumar el total de observaciones."""
        outcomes = [(i / 10.0, i % 2 == 0) for i in range(10)]

        report = calibrate(outcomes)

        assert len(report.deciles) == DEFAULT_BINS
        assert sum(bin_.count for bin_ in report.deciles) == 10
        assert report.deciles == tuple(
            sorted(report.deciles, key=lambda bin_: bin_.low)
        )


class TestCalibratePenaliza:
    def test_sobreconfianza_penaliza_brier(self):
        """Confianza 0.9 con fallo debe disparar Brier y ECE."""
        outcomes = [(0.9, False)] * 5

        report = calibrate(outcomes)

        assert report.brier == pytest.approx(0.81)
        assert report.ece == pytest.approx(0.9)
        assert is_well_calibrated(report) is False

    def test_ece_caso_calculable_a_mano(self):
        """Cinco pronosticos 0.8 con acierto dan ECE = |1.0 - 0.8| = 0.2."""
        outcomes = [(0.8, True)] * 5

        report = calibrate(outcomes)

        assert report.n == 5
        assert report.ece == pytest.approx(0.2)
        assert report.brier == pytest.approx(0.04)


class TestBinning:
    def test_equal_mass_reparte_observaciones_por_masa(self):
        """equal_mass reparte ~igual cantidad por bin (sin bins vacios)."""
        outcomes = [(0.9, True)] * 10

        report = calibrate(outcomes, bins=5, strategy=BIN_STRATEGY_EQUAL_MASS)

        assert len(report.deciles) == 5
        assert [bin_.count for bin_ in report.deciles] == [2, 2, 2, 2, 2]

    def test_equal_mass_omite_bins_vacios_si_n_menor_bins(self):
        """Con n < bins, equal_mass devuelve solo bins no vacios."""
        report = calibrate([(0.9, True)] * 5, bins=10, strategy=BIN_STRATEGY_EQUAL_MASS)

        assert len(report.deciles) == 5

    def test_equal_width_mantiene_bins_fijos(self):
        """equal_width conserva los 10 bins aunque queden vacios."""
        report = calibrate([(0.9, True)] * 10, strategy=BIN_STRATEGY_EQUAL_WIDTH)

        assert len(report.deciles) == DEFAULT_BINS
        assert sum(bin_.count for bin_ in report.deciles) == 10

    def test_estrategia_desconocida_lanza_valueerror(self):
        """Una estrategia no reconocida se rechaza con error accionable."""
        with pytest.raises(ValueError, match="estrategia desconocida"):
            calibrate([(0.5, True)] * MIN_POINTS, strategy="magic")


class TestCalibrateValida:
    def test_n_menor_min_points_lanza_valueerror(self):
        """Menos de MIN_POINTS puntos no se pueden calibrar."""
        with pytest.raises(ValueError, match=f"n<{MIN_POINTS}"):
            calibrate([(0.5, True)] * (MIN_POINTS - 1))

    def test_confianza_fuera_de_rango_lanza_valueerror(self):
        """Una confianza > 1 debe ser rechazada con error accionable."""
        with pytest.raises(ValueError, match="fuera de \\[0,1\\]"):
            calibrate([(1.5, True)] * MIN_POINTS)

    def test_acierto_no_booleano_lanza_typeerror(self):
        """Un acierto no booleano debe ser rechazado con TypeError."""
        with pytest.raises(TypeError, match="no booleano"):
            calibrate([(0.5, 1)] * MIN_POINTS)  # type: ignore[list-item]
