"""DTOs de la busqueda federada (extraccion mecanica).

FederatedResult y FederatedStats: estructuras de datos de resultado
y estadisticas de una busqueda federada multi-backend.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FederatedResult:
    """Resultado federado de busqueda multi-backend.

    Attributes:
        id: Identificador unico del registro.
        score: Puntaje de similitud normalizado (0-1, mas alto es mejor).
        payload: Metadatos asociados al vector.
        backend: Nombre del backend origen (lancedb, chroma, qdrant).
        vector: Vector original (opcional, util para MMR).
    """
    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)
    backend: str = ""
    vector: list[float] | None = None

@dataclass
class FederatedStats:
    """Estadisticas de una busqueda federada.

    Attributes:
        total_requests: Total de busquedas realizadas.
        cache_hits: Veces que se sirvio desde cache.
        cache_misses: Veces que no habia cache.
        backends_available: Cuantos backends respondieron.
        backends_total: Cuantos backends estaban configurados.
        avg_latency_ms: Latencia promedio por busqueda.
    """
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    backends_available: int = 0
    backends_total: int = 0
    avg_latency_ms: float = 0.0
