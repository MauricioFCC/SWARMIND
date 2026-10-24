"""Contrato del evaluador de factores (spec frontera 11.16 — Hubble + NVIDIA).

WHAT: verifica ``harness/alpha_mining/factor_eval.py`` contra la frontera:

- **Hubble** (arXiv 2604.09601): reporte dual RankIC + Pearson IC, scoring
  multi-métrica estandarizado y feedback estructurado accionable.
- **NVIDIA signal/code/eval** (blog NeMo Agent Toolkit, 2026-05): umbrales de
  aceptación `ic_threshold=0.02` y `p_value_threshold=0.05`; el eval agent
  acepta/rechaza y devuelve sugerencias optimizadoras al siguiente ciclo.
- **AlphaAgent** (KDD'25): el eval agent valida ejecutabilidad y estabilidad
  numérica (NaN/inf) además del poder predictivo.

WHY: sin umbrales estadísticos duros, el loop acepta ruido (backtest noise,
QuantaAlpha §1); sin RankIC, los outliers de colas pesadas falsean el IC.

WHERE: ``harness/alpha_mining/factor_eval.py``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from harness.alpha_mining.factor_dsl import Expr, Field, Operator, evaluate
from harness.alpha_mining.factor_eval import (
    DEFAULT_MIN_ABS_IC,
    DEFAULT_P_VALUE_MAX,
    EvalVerdict,
    FactorMetrics,
    decide,
    evaluate_factor,
    evaluate_values,
    forward_returns,
)
from harness.tests.fixtures_alpha import ORTHO_ROW, make_panel

_TINY_FWD = np.array([[-0.09, -0.03, 0.02, 0.08]])
_TINY_VALUES = np.array([[0.001, 0.01, 0.1, 10.0]])


def _weak_signal() -> tuple[np.ndarray, np.ndarray]:
    """Senal debil con rank_ic exacto 0.2 y 16 observaciones.

    fwd = [30, 20, 10, 40] -> ranks [2, 1, 0, 3] vs values ranks
    [0, 1, 2, 3]: Spearman = 1 - 6*8/(4*15) = 0.2 exacto (Σd² = 8).
    t = 0.2*sqrt(14)/sqrt(1-0.04) = 0.764 -> p = erfc(0.764/sqrt(2))
    = 0.445 > 0.05 (no significativo). Tile x4 filas -> n_obs = 16.

    Returns:
        (values, forward): panel de 4x4 con rank_ic = 0.2 exacto.
    """
    values = np.tile(np.array([1.0, 2.0, 3.0, 4.0]), (4, 1))
    fwd = np.tile(np.array([30.0, 20.0, 10.0, 40.0]), (4, 1))
    return values, fwd


def _corr_panel() -> dict[Field, np.ndarray]:
    """Panel con señal plantada: forward = 0.1 * cs_rank(open), open regular."""
    t, n = 6, 4
    open_ = np.tile(np.arange(1.0, n + 1.0) + np.arange(t)[:, None], (1, 1))
    close = np.zeros((t, n))
    close[0] = 100.0
    for step in range(t - 1):
        rank = open_[step].argsort().argsort() / (n - 1)
        close[step + 1] = close[step] * (1.0 + 0.1 * rank)
    return {
        Field.OPEN: open_,
        Field.CLOSE: close,
        Field.HIGH: close.copy(),
        Field.LOW: close.copy(),
        Field.VOLUME: np.ones((t, n)),
        Field.RETURNS: np.zeros((t, n)),
    }


class TestForwardReturns:
    """Horizonte forward determinista desde CLOSE (NVIDIA forward_periods)."""

    def test_horizonte_1_exacto(self) -> None:
        panel = {Field.CLOSE: np.array([[100.0], [110.0], [121.0], [133.1]])}

        fwd = forward_returns(panel, horizon=1)

        assert fwd[0, 0] == pytest.approx(0.10)
        assert fwd[2, 0] == pytest.approx(0.10)
        assert np.isnan(fwd[3, 0]), "ultima fila no tiene futuro"

    def test_horizonte_5_deja_nan_el_tramo_final(self) -> None:
        panel = {Field.CLOSE: np.full((10, 3), 100.0)}

        fwd = forward_returns(panel, horizon=5)

        assert np.isnan(fwd[5:, :]).all()
        assert np.isfinite(fwd[:5, :]).all()


class TestMetricas:
    """RankIC dual + significancia (Hubble/NVIDIA)."""

    def test_correlacion_perfecta(self) -> None:
        fwd = _TINY_FWD

        metrics = evaluate_values(fwd.copy(), fwd)

        assert metrics.ic == pytest.approx(1.0)
        assert metrics.rank_ic == pytest.approx(1.0)
        assert metrics.p_value == pytest.approx(0.0)

    def test_anticorrelacion_es_menos_uno(self) -> None:
        fwd = _TINY_FWD

        metrics = evaluate_values(-fwd, fwd)

        assert metrics.ic == pytest.approx(-1.0)

    def test_rank_ic_domina_en_rango_no_lineal(self) -> None:
        """Colas pesadas: RankIC mide monotonia, Pearson se degrada."""
        metrics = evaluate_values(_TINY_VALUES, _TINY_FWD)

        assert metrics.rank_ic == pytest.approx(1.0)
        assert metrics.ic < metrics.rank_ic

    def test_ortogonal_es_cero_exacto(self) -> None:
        values = np.tile(np.array([1.0, 2.0, 3.0, 4.0]), (4, 1))
        fwd = np.tile(ORTHO_ROW, (4, 1)) * 0.01

        metrics = evaluate_values(values, fwd)

        assert abs(metrics.ic) < 1e-12
        assert metrics.p_value == pytest.approx(1.0)

    def test_p_value_de_correlacion_debil_supera_umbral(self) -> None:
        """rank_ic=0.2 con 16 obs: t~0.76, p~0.45 > 0.05 (no significativo)."""
        values, fwd = _weak_signal()

        metrics = evaluate_values(values, fwd)

        assert metrics.rank_ic == pytest.approx(0.2)
        assert metrics.p_value > DEFAULT_P_VALUE_MAX

    def test_nan_rate_reportado(self) -> None:
        values = np.array([[1.0, np.nan], [np.nan, np.nan]])

        metrics = evaluate_values(values, np.ones((2, 2)))

        assert metrics.nan_rate == pytest.approx(0.75)


class TestDecision:
    """La aceptacion gobierna por RankIC + significancia + estabilidad."""

    def test_gate_de_rank_ic_gobierna(self) -> None:
        """min_abs_ic=0.9: Pearson decae (~0.79) pero RankIC=1.0 -> acepta."""
        metrics = evaluate_values(np.tile(_TINY_VALUES, (4, 1)), np.tile(_TINY_FWD, (4, 1)))

        verdict = decide(metrics, min_abs_ic=0.9)

        assert verdict.accepted is True, "el gate es por RankIC (robusto a colas)"

    def test_rechaza_por_p_value(self) -> None:
        values, fwd = _weak_signal()
        metrics = evaluate_values(values, fwd)

        verdict = decide(metrics)

        assert verdict.accepted is False
        assert any("p-value" in reason for reason in verdict.reasons)

    def test_rechaza_por_observaciones_insuficientes(self) -> None:
        metrics = evaluate_values(_TINY_FWD.copy(), _TINY_FWD)

        verdict = decide(metrics, min_obs=32)

        assert verdict.accepted is False
        assert any("observaciones" in reason for reason in verdict.reasons)

    def test_rechaza_por_nan_rate(self) -> None:
        values = np.full((4, 4), np.nan)
        metrics = evaluate_values(values, np.ones((4, 4)))

        verdict = decide(metrics, nan_rate_max=0.5)

        assert verdict.accepted is False
        assert any("nan" in reason for reason in verdict.reasons)

    def test_score_cero_en_rechazo(self) -> None:
        values = np.full((4, 4), np.nan)
        metrics = evaluate_values(values, np.ones((4, 4)))

        verdict = decide(metrics)

        assert verdict.score == 0.0

    def test_p_value_en_el_umbral_es_rechazado(self) -> None:
        """Canon NVIDIA: significativo solo si p < 0.05; p == 0.05 -> rechazado."""
        metrics = FactorMetrics(
            ic=0.5, rank_ic=0.5, t_stat=2.0, p_value=0.05, nan_rate=0.0, n_obs=32
        )

        verdict = decide(metrics)

        assert verdict.accepted is False, "p == umbral NO es significativo (p < 0.05)"
        assert any("p-value" in reason for reason in verdict.reasons)

    def test_score_acotado_con_metricas_hostiles(self) -> None:
        """p_value hostil negativo: el score compuesto NUNCA supera 1.0 (clamp)."""
        metrics = FactorMetrics(
            ic=0.5, rank_ic=0.5, t_stat=2.0, p_value=-1.0, nan_rate=0.0, n_obs=32
        )

        verdict = decide(metrics)

        assert verdict.accepted is True, "p negativo no viola el gate de significancia"
        assert 0.0 <= verdict.score <= 1.0, "score invariante en [0, 1] con input hostil"

    def test_umbrales_frontera_por_defecto(self) -> None:
        assert DEFAULT_MIN_ABS_IC == 0.02
        assert DEFAULT_P_VALUE_MAX == 0.05


class TestEvaluateFactor:
    """Integracion DSL + metricas + decision (pipeline del eval agent NVIDIA)."""

    def test_acepta_senal_planteada(self) -> None:
        panel = _corr_panel()

        verdict = evaluate_factor(Expr.leaf(Field.OPEN), panel)

        assert verdict.accepted is True
        assert verdict.metrics.ic == pytest.approx(1.0)
        assert verdict.reasons == ()

    def test_rechaza_factor_constante(self) -> None:
        panel = _corr_panel()
        ratio = Expr.apply(Operator.DIV, Expr.leaf(Field.CLOSE), Expr.leaf(Field.CLOSE))

        verdict = evaluate_factor(ratio, panel)

        assert verdict.accepted is False
        assert any("ic" in reason for reason in verdict.reasons)

    def test_rechaza_por_ventana_mayor_al_panel(self) -> None:
        panel = _corr_panel()
        expr = Expr.apply(Operator.TS_MEAN, Expr.leaf(Field.CLOSE), window=120)

        verdict = evaluate_factor(expr, panel)

        assert verdict.accepted is False
        assert any("nan" in reason for reason in verdict.reasons)

    def test_verdict_es_inmutable(self) -> None:
        metrics = evaluate_values(_TINY_FWD.copy(), _TINY_FWD)
        verdict = EvalVerdict(accepted=True, score=1.0, metrics=metrics, reasons=())

        with pytest.raises(FrozenInstanceError):
            verdict.accepted = False  # type: ignore[misc]

    def test_evaluate_values_sobre_panel_real_no_crash(self) -> None:
        """Integracion con panel sintetico completo (zero-crash)."""
        panel = make_panel()
        values = evaluate(Expr.leaf(Field.CLOSE), panel)

        metrics = evaluate_values(values, forward_returns(panel))

        assert 0.0 <= metrics.nan_rate <= 1.0
        assert metrics.n_obs > 0
