"""Factory de adaptadores para el paquete ``vector_store_adapter``.

Extraido mecanicamente de ``vector_store_adapter.py`` (regla AGR < 500
lineas). Contiene ``create_vector_store``, el factory method que
centraliza la creacion de adaptadores vectoriales.
"""
from __future__ import annotations

import logging
from typing import Any

from .base import VectorStoreAdapter
from .chroma import ChromaAdapter
from .lancedb import LanceDBAdapter
from .qdrant import QdrantAdapter

logger = logging.getLogger("harness.memory_rag.vector_store_adapter")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_vector_store(backend: str = "lancedb", **kwargs: Any) -> VectorStoreAdapter:
    """Factory method para crear instancias de adaptadores vectoriales.

    Selecciona y configura el adaptador segun el backend solicitado.
    Sigue el patron Abstract Factory para centralizar la creacion.

    Args:
        backend: Nombre del backend ('lancedb', 'chroma', 'qdrant').
        **kwargs: Argumentos especificos del adaptador (ej: db_path, host, port).

    Returns:
        Instancia de VectorStoreAdapter configurada.

    Raises:
        ValueError: Si el backend no es soportado.

    Examples:
        >>> store = create_vector_store("chroma", db_path="/tmp/chroma")
        >>> store = create_vector_store("qdrant", host="qdrant.example.com", port=6334)
    """
    adapters: dict[str, type] = {
        "lancedb": LanceDBAdapter,
        "chroma": ChromaAdapter,
        "qdrant": QdrantAdapter,
    }
    cls = adapters.get(backend)
    if not cls:
        raise ValueError(
            f"Backend desconocido: '{backend}'. "
            f"Opciones disponibles: {list(adapters.keys())}"
        )
    instance = cls(**kwargs)
    logger.info("VectorStoreAdapter creado: %s (backend=%s)", type(instance).__name__, backend)
    return instance
