"""Fixtures sintéticas para los contratos de alpha_mining (ciclo 11.16).

WHAT: paneles de mercado deterministas (numpy, sin datos externos) para los
contratos de ``harness/alpha_mining``: `make_panel` genera un panel OHLCV de
paseo aleatorio geometrico sembrado; `ORTHO_ROW` es una fila exactamente
ortogonal a [1, 2, 3, 4] (correlacion de Pearson = 0 exacta, para tests de
"sin señal").

WHY: los 5 sistemas frontera (QuantaAlpha/AlphaAgent/Hubble/AlphaMCTS/NVIDIA)
se validan sobre backtests; los contratos necesitan señales planteadas con
correlaciones EXACTAS, no aproximaciones aleatorias.

WHERE: `harness/tests/fixtures_alpha.py` (usado por test_factor_dsl,
test_factor_eval, test_alpha_zoo, test_mining_loop).
"""

from __future__ import annotations

import numpy as np

from harness.alpha_mining.factor_dsl import Field

#: Correlacion exacta 0 contra [1, 2, 3, 4] (covariancia nula por construccion).
ORTHO_ROW = np.array([1.0, -3.0, 3.0, -1.0])


def make_panel(seed: int = 7, t: int = 120, n: int = 6) -> dict[Field, np.ndarray]:
    """Genera un panel OHLCV determinista (paseo aleatorio geometrico).

    Args:
        seed: Semilla del generador (determinismo puro).
        t: Filas (dias de trading).
        n: Columnas (activos).

    Returns:
        Mapping Field -> ndarray float64 (t, n) con OPEN/HIGH/LOW/CLOSE/
        VOLUME/RETURNS coherentes entre si.
    """
    rng = np.random.default_rng(seed)
    drift = rng.normal(0.0, 0.01, size=(t, 1))
    shocks = rng.normal(0.0, 0.02, size=(t, n))
    close = 100.0 * np.exp(np.cumsum(drift + shocks, axis=0))
    high = close * (1.0 + np.abs(rng.normal(0.0, 0.005, size=(t, n))))
    low = close * (1.0 - np.abs(rng.normal(0.0, 0.005, size=(t, n))))
    open_ = (high + low) / 2.0
    volume = np.exp(rng.normal(0.0, 0.3, size=(t, n))) * 1e6
    returns = np.vstack([np.zeros((1, n)), close[1:] / close[:-1] - 1.0])
    return {
        Field.OPEN: open_,
        Field.HIGH: high,
        Field.LOW: low,
        Field.CLOSE: close,
        Field.VOLUME: volume,
        Field.RETURNS: returns,
    }
