"""Factory de vector stores: punto unico de construccion (ports & adapters).

La capa de aplicacion pide un ``VectorStorePort`` sin conocer la
infraestructura. Este modulo resuelve el adaptador concreto (RuscaDB por
defecto, LanceDB o in-memory) y valida el contrato antes de devolverlo.

Referencia: Clean Architecture (Martin 2017), Hexagonal (Cockburn),
ADR-0098 (puertos de dominio).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from harness.domain.ports import VectorStorePort

from .lance_vector_store import LanceVectorStore
from .ruscadb_store import RuscaDBStore

logger = logging.getLogger("harness.memory_rag.vector_store_factory")

#: Backends soportados por la factory.
SUPPORTED_BACKENDS = ("ruscadb", "lancedb", "memory")

#: Backend por defecto: RuscaDB es la persistencia unica (ciclo 11.42).
DEFAULT_BACKEND = "ruscadb"


def _resolve_backend(backend: str | None, config: Any) -> str:
    """Resuelve el backend con precedencia argumento > env > config > default.

    Args:
        backend: Backend explicito (opcional).
        config: Objeto de configuracion con ``backend``/``vector_backend``.

    Returns:
        Nombre del backend normalizado en minusculas.
    """
    if backend is None:
        backend = os.environ.get("VECTOR_BACKEND")
    if backend is None and config is not None:
        candidate = getattr(config, "vector_backend", None)
        if candidate is None:
            candidate = getattr(config, "backend", None)
        backend = getattr(candidate, "value", candidate)
    return str(backend or DEFAULT_BACKEND).lower()


def get_vector_store(
    backend: str | None = None,
    db_path: str | None = None,
    allow_fallback: bool = False,
    config: Any = None,
) -> VectorStorePort:
    """Devuelve un adaptador de memoria que cumple ``VectorStorePort``.

    Precedencia del backend:
      1. Argumento explicito.
      2. Env var ``VECTOR_BACKEND``.
      3. ``config.vector_backend`` / ``config.backend``.
      4. ``ruscadb`` (default).

    Args:
        backend: Backend pedido (``ruscadb``, ``lancedb`` o ``memory``).
        db_path: Ruta de la base; ``None`` usa el default del adaptador.
        allow_fallback: Permite degradar a LanceDB/in-memory.
        config: MemoryConfig opcional.

    Returns:
        Adaptador que implementa ``VectorStorePort``.

    Raises:
        ValueError: Si el backend pedido no esta soportado.
        TypeError: Si el adaptador construido no cumple el puerto.
    """
    resolved = _resolve_backend(backend, config)
    if resolved not in SUPPORTED_BACKENDS:
        raise ValueError(
            "get_vector_store | WHAT=backend_invalido | "
            f"WHY=no_soportado | WHERE=vector_store_factory | "
            f"backend={resolved!r} | soportados={SUPPORTED_BACKENDS}"
        )
    if resolved == "ruscadb":
        store: Any = RuscaDBStore(
            db_path=db_path, allow_fallback=allow_fallback, config=config
        )
    elif resolved == "memory":
        store = LanceVectorStore(
            db_path=db_path, allow_fallback=True, config=config, backend="memory"
        )
    else:
        store = LanceVectorStore(
            db_path=db_path, allow_fallback=allow_fallback, config=config,
            backend="lancedb",
        )
    if not isinstance(store, VectorStorePort):
        raise TypeError(
            "get_vector_store | WHAT=contrato_incumplido | "
            f"WHY=no_implementa_VectorStorePort | WHERE=vector_store_factory | "
            f"tipo={type(store).__name__} | backend={resolved}"
        )
    logger.debug("vector store listo: backend=%s tipo=%s", resolved, type(store).__name__)
    return store


__all__ = ["DEFAULT_BACKEND", "SUPPORTED_BACKENDS", "get_vector_store"]
