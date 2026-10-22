"""Factory de vector store: selecciona backend (lancedb/ruscadb/memory)."""

from __future__ import annotations

import os
from typing import Any

from .lance_vector_store import LanceVectorStore
from .ruscadb_store import RuscaDBStore


def get_vector_store(
    backend: str | None = None,
    db_path: str | None = None,
    allow_fallback: bool = False,
    config: Any = None,
) -> Any:
    """Devuelve un vector store segun el backend solicitado.

    Precedencia del backend:
      1. Argumento explicito.
      2. Env var VECTOR_BACKEND.
      3. config.vector_backend (si existe).
      4. 'lancedb' por defecto.
    """
    if backend is None:
        backend = os.environ.get("VECTOR_BACKEND")
    if backend is None and config is not None:
        backend = getattr(config, "vector_backend", None)
    backend = (backend or "lancedb").lower()
    if backend == "ruscadb":
        return RuscaDBStore(db_path=db_path, allow_fallback=allow_fallback, config=config)
    if backend == "memory":
        return LanceVectorStore(db_path=db_path, allow_fallback=True, config=config)
    return LanceVectorStore(db_path=db_path, allow_fallback=allow_fallback, config=config)