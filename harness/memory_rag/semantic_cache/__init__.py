"""Semantic Cache — Cachea respuestas de LLM por similitud semantica.

Este paquete reemplaza al modulo ``semantic_cache.py`` (regla AGR:
archivo < 500 lineas). Todos los simbolos publicos del modulo original
se re-exportan desde aqui, por lo que los imports existentes
(``from harness.memory_rag.semantic_cache import SemanticCache``) siguen
funcionando identicos.

Usa LanceDB como backend (ya integrado). Cuando un agente formula una query,
se calcula su embedding y se busca en la coleccion "semantic_cache".
Si existe una respuesta con similitud > threshold, se retorna sin llamar al LLM.

Ahorro estimado: 20-40% de llamadas LLM evitadas.
Hit rate tipico: 25-40% con threshold 0.92.
"""
from __future__ import annotations

from typing import Any

from .constants import (
    COLLECTION_SEMANTIC_CACHE,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_TTL_SECONDS,
)
from .core import SemanticCache
from .models import CacheEntry

__all__ = [
    "COLLECTION_SEMANTIC_CACHE",
    "DEFAULT_EMBEDDING_DIM",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "DEFAULT_TTL_SECONDS",
    "CacheEntry",
    "SemanticCache",
]


# ShapedCache movido a shaped_cache.py
# Import diferido para evitar circular import
def __getattr__(name: str) -> Any:
    """Lazy import de ShapedCache para compatibilidad."""
    if name == "ShapedCache":
        from harness.memory_rag.shaped_cache import ShapedCache as _sc
        return _sc
    raise AttributeError(f"module 'harness.memory_rag.semantic_cache' has no attribute '{name}'")
