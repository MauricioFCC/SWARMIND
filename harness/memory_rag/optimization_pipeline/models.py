"""Modelos de datos para el paquete ``optimization_pipeline``.

Extraido mecanicamente de ``optimization_pipeline.py`` (regla AGR < 500
lineas). Contiene ``OptimizationResult``, el DTO de resultado de una
llamada LLM optimizada.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class OptimizationResult:
    """Resultado de la optimizacion de una llamada LLM."""
    original_prompt: str = ""
    optimized_prompt: str = ""
    tokens_before: int = 0
    tokens_after: int = 0
    tokens_saved: int = 0
    compression_pct: float = 0.0
    cache_hit: bool = False
    cached_response: str = ""
    skills_loaded: list[str] = field(default_factory=list)
    budget_snapshot: dict[str, Any] = field(default_factory=dict)
    context_window: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
