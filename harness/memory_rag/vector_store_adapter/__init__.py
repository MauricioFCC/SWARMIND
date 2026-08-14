"""
VectorStoreAdapter — Abstraction for multiple vector databases.

Soporta: LanceDB (actual), Chroma (serverless), Qdrant (production).
Patron: Strategy/Adapter similar a SQLAlchemy para vectores.

Refactorizado a paquete (regla AGR: archivo < 500 lineas). Todos los
simbolos publicos del modulo original se re-exportan desde aqui, por lo
que los imports existentes
(``from harness.memory_rag.vector_store_adapter import VectorStoreAdapter``)
siguen funcionando identicos.
"""
from __future__ import annotations

from .base import VectorStoreAdapter
from .chroma import ChromaAdapter
from .factory import create_vector_store
from .lancedb import LanceDBAdapter
from .models import SearchResult
from .qdrant import QdrantAdapter

__all__ = [
    "ChromaAdapter",
    "LanceDBAdapter",
    "QdrantAdapter",
    "SearchResult",
    "VectorStoreAdapter",
    "create_vector_store",
]
