"""Tests de equivalencia para la covarianza rolling O(n) (prefix sums).

Adversariales: pares completos con NaN, ventanas all-NaN, empates numericos,
tamaños de ventana extremos, varianza ~0 (vector constante).
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.alpha_mining.factor_dsl import _ts_corr


def _naive_ts_corr(x, y, window):
    """Oráculo independiente: Pearson por ventana via ``np.corrcoef`` (O(n·W)).

    ``np.corrcoef`` usa centrado por media (implementación numpy distinta de
    la fórmula E[xy]-E[x]E[y]) → oracle cruzado contra la implementación.
    """
    out = np.full(x.shape, np.nan)
    if x.shape[0] < window:
        return out
    for column in range(x.shape[1]):
        series_a = x[:, column]
        series_b = y[:, column]
        for t in range(window - 1, x.shape[0]):
            xa = series_a[t - window + 1 : t + 1]
            xb = series_b[t - window + 1 : t + 1]
            mask = np.isfinite(xa) & np.isfinite(xb)
            if int(mask.sum()) < 2:
                continue
            corr = np.corrcoef(xa[mask], xb[mask])[0, 1]
            if np.isfinite(corr):
                out[t, column] = float(corr)
    return out


class TestTsCorrEquivalence:
    """Prefix sums O(n) vs referencia ingenua O(n*W): mismos resultados."""

    @pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
    def test_matches_naive_with_nan_mask(self, seed):
        """Paneles con NaN intercalados producen la misma correlacion."""
        rng = np.random.default_rng(seed)
        x = np.round(rng.normal(0.0, 1.0, size=(40, 3)), 4)
        y = np.roll(x, 2, axis=0) + rng.normal(0, 0.1, x.shape)
        y = np.round(y, 4)
        mask = rng.random(x.shape) < 0.15
        x[mask] = np.nan
        y[np.roll(mask, 1, axis=0)] = np.nan
        expected = _naive_ts_corr(x, y, 7)
        got = _ts_corr(x, y, 7)
        np.testing.assert_allclose(got, expected, atol=1e-9, rtol=1e-9, equal_nan=True)

    def test_window_gt_rows_is_all_nan(self):
        """Ventana mayor que la serie: todo NaN, sin crash."""
        x = np.arange(10.0).reshape(5, 2)
        assert np.isnan(_ts_corr(x, x, 50)).all()

    def test_window_equals_rows_single_corr(self):
        """window == T produce una unica correlacion valide al final."""
        x = np.arange(1.0, 11.0).reshape(10, 1)
        got = _ts_corr(x, x * 2.0, 10)
        assert np.isnan(got[:-1]).all()
        np.testing.assert_allclose(got[-1, 0], 1.0, atol=1e-9)

    def test_all_nan_window_is_nan(self):
        """Ventana todo-NaN: NaN sin division por 0 ni runtime warning."""
        x = np.full((10, 2), np.nan)
        y = np.full((10, 2), np.nan)
        with np.errstate(invalid="raise", divide="raise"):
            got = _ts_corr(x, y, 3)
        assert np.isfinite(got).sum() == 0

    def test_constant_series_is_nan_no_div0(self):
        """Serie constante (varianza ~0): salida NaN, sin division por 0."""
        x = np.ones((10, 1))
        with np.errstate(divide="raise", invalid="raise"):
            got = _ts_corr(x, x, 3)
        assert np.isnan(got[-1, 0])

    def test_perfect_positive_and_negative(self):
        """Correlacion perfecta +/-1 con jitter minimo permitido (#float)."""
        t = np.arange(1.0, 31.0).reshape(30, 1)
        pos = _ts_corr(t, 3.0 * t + 1.0, 5)
        neg = _ts_corr(t, -2.0 * t + 5.0, 5)
        np.testing.assert_allclose(pos[-1, 0], 1.0, atol=1e-9)
        np.testing.assert_allclose(neg[-1, 0], -1.0, atol=1e-9)

    def test_mask_pair_complete_semantics(self):
        """Solo cuenta pares donde AMBOS son finitos (mirror de la spec)."""
        x = np.array([[1.0], [2.0], [3.0], [4.0]])
        y = np.array([[np.nan], [2.0], [3.0], [4.0]])
        expected = _naive_ts_corr(x, y, 3)
        got = _ts_corr(x, y, 3)
        np.testing.assert_allclose(got[2, 0], expected[2, 0], atol=1e-9)