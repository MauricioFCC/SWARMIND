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

__all__ = ["Fenwick", "ts_rank"]


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
