"""Data transfer objects para el paquete ``vector_store_adapter``.

Extraido mecanicamente de ``vector_store_adapter.py`` (regla AGR < 500
lineas). Contiene ``SearchResult``, el DTO de resultados de busqueda
vectorial usado por todos los adaptadores.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """Resultado de una busqueda vectorial.

    Attributes:
        id: Identificador unico del resultado.
        score: Puntaje de similitud (0-1, mas alto es mejor).
        payload: Metadatos asociados al vector.
        vector: Vector original (opcional, util para debugging).
    """
    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)
    vector: list[float] | None = None
