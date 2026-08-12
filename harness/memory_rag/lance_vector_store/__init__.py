"""Vector store unificado para RAG y busqueda de metadatos con LanceDB.

Este paquete reemplaza al modulo ``lance_vector_store.py`` (regla AGR:
archivo < 500 lineas). Todos los simbolos publicos del modulo original
se re-exportan desde aqui, por lo que los imports existentes
(``from harness.memory_rag.lance_vector_store import LanceVectorStore``)
siguen funcionando identicos.

LanceDB es OBLIGATORIO. Si no esta disponible, se lanza un error claro.
El fallback in-memory solo se activa con allow_fallback=True (emergencias/test).
"""
from __future__ import annotations

# Path se re-exporta para compatibilidad con parches de tests que usan
# ``patch("harness.memory_rag.lance_vector_store.Path.mkdir")``.
from pathlib import Path  # noqa: F401

from ..lance_schemas import DEFAULT_COLLECTIONS
from ..memory_config import MemoryConfig, get_memory_config
from .constants import (
    COLLECTION_PROCEDURAL_SKILLS,
    COLLECTION_PROMPT_EVOLUTION_LOG,
    COLLECTION_SCHEDULER_LOG,
    LANCEDB_ROOT,
)
from .core import LanceVectorStore
from .exceptions import CollectionNotFoundError, VectorStoreError
from .models import _Collection, _StoredItem

__all__ = [
    "COLLECTION_PROCEDURAL_SKILLS",
    "COLLECTION_PROMPT_EVOLUTION_LOG",
    "COLLECTION_SCHEDULER_LOG",
    "DEFAULT_COLLECTIONS",
    "LANCEDB_ROOT",
    "CollectionNotFoundError",
    "LanceVectorStore",
    "MemoryConfig",
    "VectorStoreError",
    "_Collection",
    "_StoredItem",
    "get_memory_config",
]
