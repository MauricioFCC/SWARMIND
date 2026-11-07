"""Evaluador de factores (spec frontera 11.16 — Hubble + NVIDIA + AlphaAgent).

WHAT: backtest determinista de factores con las metricas de la frontera:

- **Hubble** (arXiv 2604.09601): reporte DUAL RankIC + Pearson IC
  (RankIC robusto a colas pesadas) y scoring multi-metrica estandarizado.
- **NVIDIA signal/code/eval** (blog NeMo Agent Toolkit, 2026-05): umbrales de
  aceptacion del eval agent — `ic_threshold=0.02`, `p_value_threshold=0.05`;
  rechazos producen sugerencias accionables que realimentan el loop.
- **AlphaAgent** (KDD'25): el eval agent valida estabilidad numerica (NaN
  rate) ademas del poder predictivo.

Metricas: IC = media de correlaciones de Pearson cross-seccionales por
fila factor vs retorno forward; RankIC = igual sobre midranks (Spearman
CS); t = rank_ic * sqrt(n_obs - 2) / sqrt(1 - rank_ic^2) (aproximacion
pooled); p = erfc(|t| / sqrt(2)) (cola normal bicolateral).

WHY: sin umbrales duros el loop acepta backtest noise (QuantaAlpha §1);
sin RankIC los outliers falsean el IC; sin NaN-rate un factor quebrado
pasa como "poco correlacionado".

WHERE: ``harness/alpha_mining/factor_eval.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from harness.alpha_mining.factor_dsl import EPS, Expr, Field, evaluate

#: RankIC absoluto minimo de aceptacion (canon NVIDIA: IC > 0.02).
DEFAULT_MIN_ABS_IC = 0.02
#: p-value maximo de la significancia (canon NVIDIA: p < 0.05).
DEFAULT_P_VALUE_MAX = 0.05
#: Observaciones minimas (pares validos) para confiar en la metrica.
DEFAULT_MIN_OBS = 16
#: Fraccion maxima de NaN tolerada en los valores del factor.
NAN_RATE_MAX = 0.5
#: Atributos minimos por fila cross-seccional para correlacionar.
_MIN_ASSETS_PER_ROW = 3
#: Tope de t-stat para correlacion perfecta (evita division por cero).
_TSTAT_CAP = 1e6
#: Normalizacion del componente de signal en el score (Hubble multi-metrica).
_IC_NORM_CAP = 0.10


@dataclass(frozen=True)
class FactorMetrics:
    """Metricas crudas de un factor contra retornos forward.

    Attributes:
        ic: Pearson IC cross-seccional promedio (media de corr. por fila).
        rank_ic: RankIC (Spearman CS) promedio — metrica de aceptacion.
        t_stat: t pooled derivado del rank_ic (significancia).
        p_value: p-value bicolateral (cola normal) del t.
        nan_rate: Fraccion de NaN en los valores del factor.
        n_obs: Pares (factor, retorno) validos usados.
    """

    ic: float
    rank_ic: float
    t_stat: float
    p_value: float
    nan_rate: float
    n_obs: int


@dataclass(frozen=True)
class EvalVerdict:
    """Veredicto del eval agent sobre un factor.

    Attributes:
        accepted: True si el factor pasa todos los umbrales.
        score: Score compuesto [0, 1] (0 si rechazado).
        metrics: Metricas crutas.
        reasons: Rechazos legibles (sugerencias de optimizacion).
    """

    accepted: bool
    score: float
    metrics: FactorMetrics
    reasons: tuple[str, ...]


def forward_returns(panel: dict[Field, NDArray[np.float64]], horizon: int = 1) -> NDArray[np.float64]:
    """Retornos forward desde CLOSE (NVIDIA forward_periods).

    Args:
        panel: Panel OHLCV con Field.CLOSE (T, N).
        horizon: Dias hacia adelante.

    Returns:
        ndarray (T, N): ``close[t+h]/close[t] - 1`` con las ultimas h filas
        en NaN (no tienen futuro observado).
    """
    close = np.asarray(panel[Field.CLOSE], dtype=float)
    fwd = np.full(close.shape, np.nan)
    if horizon < close.shape[0]:
        fwd[:-horizon] = close[horizon:] / close[:-horizon] - 1.0
    return fwd


def evaluate_values(
    values: NDArray[np.float64], forward: NDArray[np.float64]
) -> FactorMetrics:
    """Computa IC/RankIC/t/p/nan_rate de valores ya calculados.

    Args:
        values: Valores del factor (T, N).
        forward: Retornos forward (T, N) alineados.

    Returns:
        Metricas del factor (todas finitas; 0.0 si no hay filas validas).

    Raises:
        ValueError: Si las formas no coinciden.
    """
    values = np.asarray(values, dtype=float)
    forward = np.asarray(forward, dtype=float)
    if values.shape != forward.shape:
        raise ValueError(
            f"WHAT: values {values.shape} != forward {forward.shape}. "
            "WHY: se correlacionan celda a celda. WHERE: evaluate_values."
        )
    ics, rank_ics = _row_correlations(values, forward)
    n_obs = int((np.isfinite(values) & np.isfinite(forward)).sum())
    nan_rate = float(np.isnan(values).mean()) if values.size else 1.0
    ic = float(np.mean(ics)) if ics else 0.0
    rank_ic = float(np.mean(rank_ics)) if rank_ics else 0.0
    t_stat = _pooled_t(rank_ic, n_obs)
    return FactorMetrics(
        ic=ic,
        rank_ic=rank_ic,
        t_stat=t_stat,
        p_value=_p_value(t_stat),
        nan_rate=nan_rate,
        n_obs=n_obs,
    )


def decide(
    metrics: FactorMetrics,
    *,
    min_abs_ic: float = DEFAULT_MIN_ABS_IC,
    p_value_max: float = DEFAULT_P_VALUE_MAX,
    min_obs: int = DEFAULT_MIN_OBS,
    nan_rate_max: float = NAN_RATE_MAX,
) -> EvalVerdict:
    """Aplica los umbrales del eval agent y produce veredicto + sugerencias.

    La aceptacion gobierna por |RankIC| (robusto a colas pesadas, canon
    Hubble/NVIDIA); los rechazos listan TODAS las violaciones (feedback
    accionable para la siguiente iteracion del loop).

    Args:
        metrics: Metricas crutas.
        min_abs_ic: Umbral de |RankIC|.
        p_value_max: Umbral de significancia.
        min_obs: Observaciones minimas.
        nan_rate_max: Fraccion maxima de NaN.

    Returns:
        Veredicto inmutable con razones legibles (vacio si acepta).
    """
    reasons: list[str] = []
    if metrics.n_obs < min_obs:
        reasons.append(f"observaciones {metrics.n_obs} < minimas {min_obs}")
    if abs(metrics.rank_ic) < min_abs_ic:
        reasons.append(
            f"rank_ic {metrics.rank_ic:.4f} < umbral {min_abs_ic:.2f}"
        )
    if metrics.p_value >= p_value_max:
        reasons.append(f"p-value {metrics.p_value:.3f} >= maximo {p_value_max:.2f}")
    if metrics.nan_rate > nan_rate_max:
        reasons.append(f"nan_rate {metrics.nan_rate:.2f} > maximo {nan_rate_max:.2f}")
    accepted = not reasons
    return EvalVerdict(
        accepted=accepted,
        score=_composite_score(metrics) if accepted else 0.0,
        metrics=metrics,
        reasons=tuple(reasons),
    )


def evaluate_factor(
    expr: Expr,
    panel: dict[Field, NDArray[np.float64]],
    *,
    horizon: int = 1,
    min_abs_ic: float = DEFAULT_MIN_ABS_IC,
    p_value_max: float = DEFAULT_P_VALUE_MAX,
    min_obs: int = DEFAULT_MIN_OBS,
    nan_rate_max: float = NAN_RATE_MAX,
) -> EvalVerdict:
    """Pipeline completo: DSL -> valores -> metricas -> decision.

    Args:
        expr: AST del factor.
        panel: Panel OHLCV.
        horizon: Horizonte forward.
        min_abs_ic: Umbral de |RankIC|.
        p_value_max: Umbral de significancia.
        min_obs: Observaciones minimas.
        nan_rate_max: Fraccion maxima de NaN.

    Returns:
        Veredicto del eval agent.
    """
    values = evaluate(expr, panel)
    metrics = evaluate_values(values, forward_returns(panel, horizon))
    return decide(
        metrics,
        min_abs_ic=min_abs_ic,
        p_value_max=p_value_max,
        min_obs=min_obs,
        nan_rate_max=nan_rate_max,
    )


def _row_correlations(
    values: NDArray[np.float64], forward: NDArray[np.float64]
) -> tuple[list[float], list[float]]:
    """Correlaciones cross-seccionales por fila (Pearson y Spearman)."""
    ics: list[float] = []
    rank_ics: list[float] = []
    for row in range(values.shape[0]):
        ic = _pearson(values[row], forward[row])
        if not math.isnan(ic):
            ics.append(ic)
            rank_ics.append(_spearman(values[row], forward[row]))
    return ics, rank_ics


def _pearson(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    """Pearson nan-aware de dos vectores (NaN si no hay varianza/muestras)."""
    valid = np.isfinite(a) & np.isfinite(b)
    if int(valid.sum()) < _MIN_ASSETS_PER_ROW:
        return math.nan
    av, bv = a[valid], b[valid]
    da, db = av - av.mean(), bv - bv.mean()
    denom = math.sqrt(float(da @ da) * float(db @ db))
    if denom < EPS:
        return math.nan
    return float((da @ db) / denom)


def _midranks(vector: NDArray[np.float64]) -> NDArray[np.float64]:
    """Midranks deterministas (ties por posicion; sin dependencias externas)."""
    order = np.argsort(vector, kind="stable")
    ranks = np.empty(len(vector), dtype=float)
    ranks[order] = np.arange(len(vector), dtype=float)
    return ranks


def _spearman(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    """Spearman CS: Pearson sobre midranks de la fila valida."""
    valid = np.isfinite(a) & np.isfinite(b)
    return _pearson(_midranks(a[valid]), _midranks(b[valid]))


def _pooled_t(rank_ic: float, n_obs: int) -> float:
    """t pooled: rank_ic * sqrt(n-2) / sqrt(1 - rank_ic^2), acotado."""
    denom = math.sqrt(max(1.0 - rank_ic**2, EPS))
    raw = rank_ic * math.sqrt(max(n_obs - 2, 1)) / denom
    return float(np.clip(raw, -_TSTAT_CAP, _TSTAT_CAP))


def _p_value(t_stat: float) -> float:
    """p-value bicolateral cola normal desde t."""
    if not math.isfinite(t_stat):
        return 0.0 if t_stat > 0 else 1.0
    return math.erfc(abs(t_stat) / math.sqrt(2.0))


def _composite_score(metrics: FactorMetrics) -> float:
    """Score compuesto estandarizado [0, 1] (Hubble multi-metrica).

    50% signal (|rank_ic| normalizado por ``_IC_NORM_CAP``) + 50%
    significancia (1 - p_value). Ambos acotados a [0, 1].
    """
    signal = min(abs(metrics.rank_ic) / _IC_NORM_CAP, 1.0)
    significance = min(1.0 - metrics.p_value, 1.0)
    return round(0.5 * signal + 0.5 * significance, 6)
