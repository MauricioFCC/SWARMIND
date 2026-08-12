"""ModelRouter — Enrutamiento por complejidad semantica (ADR-0041 H7).

Antes: harness/model_router/complexity_router.py (539 lineas).
Ahora: paquete ``harness/model_router/complexity_router/`` con submódulos
cohesivos (constants.py, models.py, signals.py, routing.py, core.py).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos (y las
constantes internas usadas por tests y router.py) del modulo original
para mantener backward-compat:

    from harness.model_router.complexity_router import ComplexityRouter

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from .constants import (
    DEFAULT_THRESHOLD,
    KEYWORD_COMPLEX_DOMAINS,
    KEYWORD_REASONING,
    LONG_HIGH,
    LONG_LOW,
    LONG_MED,
    ROUTE_FRONTIER,
    ROUTE_SMALL,
    SCORE_COMPLEX_DOMAIN,
    SCORE_KEYWORD_REASONING,
    SCORE_LENGTH_HIGH,
    SCORE_LENGTH_MEDIUM,
    SCORE_MAX,
    SCORE_MIN,
    SCORE_MULTI_INSTRUCTION,
    SCORE_REASONING_MAX,
    SCORE_SHORT_TASK,
    SCORE_SIMPLE_TERM,
    SIGNAL_DOMAIN_COMPLEX,
    SIGNAL_KEYWORD_REASONING,
    SIGNAL_LONG_HIGH,
    SIGNAL_LONG_MEDIUM,
    SIGNAL_MULTI_INSTRUCTION,
    SIGNAL_SHORT_TASK,
    SIGNAL_SIMPLE_TASK_TERM,
    SIMPLE_TASK_TERMS,
)
from .core import ComplexityRouter
from .models import ComplexityDecision, ComplexityResult

__all__ = [
    "DEFAULT_THRESHOLD",
    "KEYWORD_COMPLEX_DOMAINS",
    "KEYWORD_REASONING",
    "LONG_HIGH",
    "LONG_LOW",
    "LONG_MED",
    "ROUTE_FRONTIER",
    "ROUTE_SMALL",
    "SCORE_COMPLEX_DOMAIN",
    "SCORE_KEYWORD_REASONING",
    "SCORE_LENGTH_HIGH",
    "SCORE_LENGTH_MEDIUM",
    "SCORE_MAX",
    "SCORE_MIN",
    "SCORE_MULTI_INSTRUCTION",
    "SCORE_REASONING_MAX",
    "SCORE_SHORT_TASK",
    "SCORE_SIMPLE_TERM",
    "SIGNAL_DOMAIN_COMPLEX",
    "SIGNAL_KEYWORD_REASONING",
    "SIGNAL_LONG_HIGH",
    "SIGNAL_LONG_MEDIUM",
    "SIGNAL_MULTI_INSTRUCTION",
    "SIGNAL_SHORT_TASK",
    "SIGNAL_SIMPLE_TASK_TERM",
    "SIMPLE_TASK_TERMS",
    "ComplexityDecision",
    "ComplexityResult",
    "ComplexityRouter",
]
