"""MetaClaw — paquete (extraccion mecanica).

Re-exporta todos los simbolos publicos del modulo original
`metaclaw.py` para mantener backward-compatibility.
"""
from .constants import (
    ALPHA_PRIOR,
    BETA_PRIOR,
    COST_PENALTY_THRESHOLD,
    DEFAULT_WINDOW_SIZE,
    EXPLORATION_NOISE,
    LATENCY_PENALTY_THRESHOLD,
    TASK_VECTOR_DIM,
    WEIGHT_CONFIDENCE,
    WEIGHT_COST,
    WEIGHT_LATENCY,
    WEIGHT_SUCCESS,
)
from .core import MetaClaw
from .models import SelectionRecord, ToolRecord

__all__ = [
    "ALPHA_PRIOR",
    "BETA_PRIOR",
    "COST_PENALTY_THRESHOLD",
    "DEFAULT_WINDOW_SIZE",
    "EXPLORATION_NOISE",
    "LATENCY_PENALTY_THRESHOLD",
    "TASK_VECTOR_DIM",
    "WEIGHT_CONFIDENCE",
    "WEIGHT_COST",
    "WEIGHT_LATENCY",
    "WEIGHT_SUCCESS",
    "MetaClaw",
    "SelectionRecord",
    "ToolRecord",
]
