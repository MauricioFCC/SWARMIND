"""Federated Search — paquete (extraccion mecanica).

Re-exporta todos los simbolos publicos del modulo original
`federated_search.py` para mantener backward-compatibility.
"""
from .constants import (
    _DEFAULT_BACKENDS,
    DEFAULT_CACHE_MAX_SIZE,
    DEFAULT_CACHE_TTL_SEC,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_MMR_LAMBDA,
    DEFAULT_TOP_K_PER_BACKEND,
)
from .core import FederatedVectorSearch
from .factory import create_federated_search
from .models import FederatedResult, FederatedStats

__all__ = [
    "DEFAULT_CACHE_MAX_SIZE",
    "DEFAULT_CACHE_TTL_SEC",
    "DEFAULT_EMBEDDING_DIM",
    "DEFAULT_MMR_LAMBDA",
    "DEFAULT_TOP_K_PER_BACKEND",
    "_DEFAULT_BACKENDS",
    "FederatedResult",
    "FederatedStats",
    "FederatedVectorSearch",
    "create_federated_search",
]
