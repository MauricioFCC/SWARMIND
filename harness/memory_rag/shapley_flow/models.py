"""Modelos de datos para el paquete ``shapley_flow``.

Extraido mecanicamente de ``shapley_flow.py`` (regla AGR < 500 lineas).
Contiene ``ShapleyAllocation`` (resultado publico) y ``_SectionFeatures``
(caracteristicas internas para el modelo de valor).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ShapleyAllocation:
    """Resultado de asignacion para una seccion del prompt.

    Attributes:
        section: Nombre de la seccion (ej: "system", "user", "rag").
        shapley_value: Contribucion marginal normalizada [0, 1].
        token_budget: Tokens asignados a esta seccion.
        original_tokens: Cantidad original de tokens de la seccion.
        marginal_contributions: Lista de contribuciones marginales
            calculadas durante la evaluacion (depuracion).
    """

    section: str
    shapley_value: float
    token_budget: int
    original_tokens: int
    marginal_contributions: list[float] = field(default_factory=list)


@dataclass
class _SectionFeatures:
    """Caracteristicas extraidas de una seccion para el modelo de valor."""

    name: str
    text: str
    token_count: int
    semantic_density: float = 0.5
    position_index: int = 0
    keyword_relevance: float = 0.5
    has_code: bool = False
