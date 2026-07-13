"""
Embeddings — Funcion de embedding centralizada (FUENTE UNICA).

Delega en ``harness.common.fallback_embedding`` que es la implementacion
unica tras el refactor DRY (reemplaza 13+ implementaciones duplicadas).

Uso:
    from harness.memory_rag.embeddings import make_embedding
    vec = make_embedding("texto a embedder")
"""

from __future__ import annotations

import numpy as np

from harness.common import fallback_embedding as _fallback

EMBEDDING_DIM = 384


def make_embedding(text: str, dim: int = EMBEDDING_DIM) -> np.ndarray:
    """
    Embedding deterministico basado en frecuencia de caracteres.

    Delega en ``harness.common.fallback_embedding``.

    Args:
        text: Texto a embedder.
        dim: Dimension del vector (default: 384).

    Returns:
        Vector numpy normalizado de dimension `dim`.
    """
    return _fallback(text, dim=dim)
