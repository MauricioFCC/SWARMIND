"""Rank rolling con Fenwick (O(T log m) por columna).

Extraido de ``factor_dsl`` para mantener el modulo del DSL por debajo del
limite AGR (500 lineas) y para que el algoritmo sea reutilizable/testeable de
forma aislada.

Formula (Fenwick / BIT, 1-based):

    add(i, delta):    mientras i <= m: tree[i] += delta; i += i & -i
    prefix(i):        mientras i > 0: acc += tree[i]; i -= i & -i

La ventana deslizante mantiene el conteo de cada valor comprimido: el rank
(midrank) del valor actual se obtiene con dos ``prefix`` en O(log m).
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

#: Epsilon numerica (espejo de factor_dsl.EPS) para varianza ~ 0.
_EPS = 1e-12

__all__ = ["Fenwick", "ts_corr", "ts_rank"]


class Fenwick:
    """Arbol de Fenwick (BIT) para conteos con updates O(log n).

    Args:
        size: Numero de posiciones (1-based en ``add``/``prefix``).
    """

    __slots__ = ("_size", "_tree")

    def __init__(self, size: int) -> None:
        self._size = size
        self._tree = [0] * (size + 1)

    def add(self, index: int, delta: int) -> None:
        """Suma ``delta`` a la posicion ``index`` (1-based)."""
        while 0 < index <= self._size:
            self._tree[index] += delta
            index += index & -index

    def prefix(self, index: int) -> int:
        """Suma acumulada de ``1..index`` (0 si ``index`` <= 0)."""
        total = 0
        while index > 0:
            total += self._tree[index]
            index -= index & -index
        return total


def _rank_column(series: NDArray[np.float64], window: int) -> NDArray[np.float64]:
    """Rank rolling de una sola columna (midrank, NaN-safe)."""
    out = np.full(series.shape, np.nan)
    finite = np.isfinite(series)
    if int(finite.sum()) < 2:
        return out
    unique = np.unique(series[finite])
    rank_of: dict[float, int] = {
        float(value): index + 1 for index, value in enumerate(unique)
    }
    tree = Fenwick(len(unique))
    in_window = 0
    for t in range(series.shape[0]):
        current = series[t]
        if np.isfinite(current):
            tree.add(rank_of[float(current)], 1)
            in_window += 1
        expired = t - window
        if expired >= 0 and np.isfinite(series[expired]):
            tree.add(rank_of[float(series[expired])], -1)
            in_window -= 1
        if t < window - 1 or not np.isfinite(current) or in_window < 2:
            continue
        rank = rank_of[float(current)]
        below = tree.prefix(rank - 1)
        equal = tree.prefix(rank) - below
        out[t] = (below + (equal - 1) / 2.0) / (in_window - 1)
    return out


def ts_corr(a: Any, b: Any, window: int) -> NDArray[np.float64]:
    """Correlacion Pearson rolling O(n) por pares completos (prefix sums).

    ``corr = (n*Sab - Sa*Sb) / (sqrt(n*Saa-Sa^2) * sqrt(n*Sbb-Sb^2))`` con
    sumas S[t]-S[t-W] 0-padded (Scan de Blelloch); O(n*W) -> O(n).

    Args:
        a: Panel (T, N) de valores (puede contener NaN).
        b: Panel (T, N) de valores (puede contener NaN).
        window: Tamano de la ventana rolling (<= 1 o > T -> todo NaN).

    Returns:
        Panel (T, N) con la correlacion en [-1, 1]; NaN donde < 2 pares
        completos o varianza ~ 0.

    Raises:
        ValueError: Si la shape de ``a`` y ``b`` no coinciden.
    """
    left = np.asarray(a, dtype=float)
    right = np.asarray(b, dtype=float)
    if left.shape != right.shape:
        raise ValueError(
            "ts_corr | WHAT=shape_mismatch | "
            f"WHY=a_b_deben_misma_forma | WHERE=ts_corr | "
            f"a={left.shape} b={right.shape}"
        )
    if window <= 1 or left.shape[0] < window:
        return np.full(left.shape, np.nan)
    return _corr_from_ends(left.shape, window, _prefix_ends(left, right))


def _prefix_ends(
    left: NDArray[np.float64], right: NDArray[np.float64]
) -> dict[str, NDArray[np.float64]]:
    """Prefix sums 0-padded para a/b/ab/aa/bb y contador de pares.

    Args:
        left: Panel (T, N) de la serie a (con NaN).
        right: Panel (T, N) de la serie b (con NaN).

    Returns:
        Dict ``{aa, ab, a, b, bb, n}`` con arrays (T+1, N) 0-alineados.
    """
    mask = np.isfinite(left) & np.isfinite(right)
    m = mask.astype(float)
    pair_a = np.where(mask, left, 0.0)
    pair_b = np.where(mask, right, 0.0)
    zeros = np.zeros((1, left.shape[1]))
    return {
        "aa": np.concatenate((zeros, np.cumsum(pair_a * pair_a, axis=0))),
        "ab": np.concatenate((zeros, np.cumsum(pair_a * pair_b, axis=0))),
        "a": np.concatenate((zeros, np.cumsum(pair_a, axis=0))),
        "b": np.concatenate((zeros, np.cumsum(pair_b, axis=0))),
        "bb": np.concatenate((zeros, np.cumsum(pair_b * pair_b, axis=0))),
        "n": np.concatenate((zeros, np.cumsum(m, axis=0))),
    }


def _corr_from_ends(
    shape: tuple[int, ...],
    window: int,
    ends: dict[str, NDArray[np.float64]],
) -> NDArray[np.float64]:
    """Pearson por ventana desde los ends 0-padded (NaN si invalida)."""
    out = np.full(shape, np.nan)
    now = slice(window, None)          # indices T >= window (0-pad ECC)
    past = slice(0, -window)           # indices t - window
    n = ends["n"][now] - ends["n"][past]
    sum_a = ends["a"][now] - ends["a"][past]
    sum_b = ends["b"][now] - ends["b"][past]
    sum_ab = ends["ab"][now] - ends["ab"][past]
    sum_aa = ends["aa"][now] - ends["aa"][past]
    sum_bb = ends["bb"][now] - ends["bb"][past]
    cov = sum_ab * n - sum_a * sum_b
    var_a = sum_aa * n - sum_a * sum_a
    var_b = sum_bb * n - sum_b * sum_b
    denom = np.sqrt(np.maximum(var_a, 0.0) * np.maximum(var_b, 0.0))
    corr = cov / np.where(denom > 0.0, denom, 1.0)
    valid = (n >= 2) & (denom > 0.0)
    out[window - 1 :] = np.where(valid, corr, np.nan)
    return out


def ts_rank(x: Any, window: int) -> NDArray[np.float64]:
    """Rank del ultimo valor dentro de la ventana (midrank, por columna).

    Args:
        x: Panel ``(T, N)`` de valores (puede contener NaN).
        window: Tamano de la ventana rolling (``<= 1`` o ``> T`` -> todo NaN).

    Returns:
        Panel ``(T, N)`` con el midrank normalizado en ``[0, 1]`` (NaN donde no
        hay al menos 2 valores finitos en la ventana).
    """
    array = np.asarray(x, dtype=float)
    out = np.full(array.shape, np.nan)
    if window <= 1 or array.shape[0] < window:
        return out
    for column in range(array.shape[1]):
        out[:, column] = _rank_column(array[:, column], window)
    return out
