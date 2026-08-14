"""Factory de alto nivel (extraccion mecanica).

Crea una instancia de FederatedVectorSearch con configuracion
simplificada a partir de backends opcionales.
"""
from __future__ import annotations

from harness.memory_rag.vector_store_adapter import VectorStoreAdapter

from .constants import (
    DEFAULT_CACHE_MAX_SIZE,
    DEFAULT_CACHE_TTL_SEC,
    DEFAULT_MMR_LAMBDA,
)
from .core import FederatedVectorSearch


def create_federated_search(
    backends: dict[str, VectorStoreAdapter] | None = None,
    mmr_lambda: float = DEFAULT_MMR_LAMBDA,
    cache_max_size: int = DEFAULT_CACHE_MAX_SIZE,
    cache_ttl: float = DEFAULT_CACHE_TTL_SEC,
) -> FederatedVectorSearch:
    """Crea un FederatedVectorSearch con configuracion simplificada.

    Args:
        backends: Dict nombre -> adaptador. Si None, usa defaults.
        mmr_lambda: Factor de balance MMR (0-1).
        cache_max_size: TamaÃ±o maximo del cache.
        cache_ttl: TTL en segundos del cache.

    Returns:
        Instancia de FederatedVectorSearch lista para usar.

    Example:
        >>> fvs = create_federated_search()
        >>> resultados = fvs.search([0.1]*384, "skills", top_k=3)
    """
    return FederatedVectorSearch(
        backends=backends,
        mmr_lambda=mmr_lambda,
        cache_max_size=cache_max_size,
        cache_ttl=cache_ttl,
    )
