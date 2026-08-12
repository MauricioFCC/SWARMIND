"""Constantes y helpers numericos para el paquete ``shapley_flow``.

Extraido mecanicamente de ``shapley_flow.py`` (regla AGR < 500 lineas).
Contiene los pesos de la funcion caracteristica, el umbral minimo de
secciones y la cache de factoriales con su helper ``_factorial``.
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Pesos para el calculo de la funcion caracteristica
WEIGHT_TOKEN_COUNT = 0.30
WEIGHT_SEMANTIC_DENSITY = 0.25
WEIGHT_POSITION_PREMIUM = 0.20
WEIGHT_KEYWORD_MATCH = 0.15
WEIGHT_LENGTH_PENALTY = 0.10

# Umbral de seccion huérfana (token count por debajo se ignora)
MIN_SECTION_TOKENS = 10

# Cache de factoriales precomputados hasta 12 (soporta hasta 12 secciones)
_FACTORIAL_CACHE: dict[int, int] = {i: math.factorial(i) for i in range(13)}


def _factorial(n: int) -> int:
    """Retorna factorial con cache para valores pequenos."""
    if n < 0:
        raise ValueError(
            f"WHAT: factorial({n}) no esta definido para negativos. "
            f"WHY: El factorial solo existe para enteros no negativos. "
            f"WHERE: shapley_flow._factorial"
        )
    if n <= 12:
        return _FACTORIAL_CACHE.get(n, math.factorial(n))
    return math.factorial(n)
