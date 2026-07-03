"""
Embeddings — Funcion de embedding centralizada (FUENTE UNICA).

Reemplaza las implementaciones duplicadas de _make_embedding / _default_embedding
que estaban dispersas en hermes_bridge.py, semantic_cache.py, agent_bus.py,
agent_dispatcher.py, context_assembler.py, etc.

Uso:
    from harness.memory_rag.embeddings import make_embedding
    vec = make_embedding("texto a embedder")
"""

from __future__ import annotations

import numpy as np

EMBEDDING_DIM = 384


def make_embedding(text: str, dim: int = EMBEDDING_DIM) -> np.ndarray:
    """
    Embedding deterministico basado en frecuencia de caracteres.
    
    No requiere modelo ML. Produce vectores normalizados de dimension fija.
    Adecuado para busqueda por similitud basica y cache semantico.
    
    Para produccion con alta precision, reemplazar con sentence-transformers:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('all-MiniLM-L6-v2')
        vec = model.encode(text)
    
    Args:
        text: Texto a embedder.
        dim: Dimension del vector (default: 384).
    
    Returns:
        Vector numpy normalizado de dimension `dim`.
    """
    if not text:
        return np.zeros(dim, dtype=np.float32)
    
    vec = np.zeros(dim, dtype=np.float32)
    for i, ch in enumerate(text.encode("utf-8", errors="replace")):
        idx = (i * 7 + ch) % dim
        vec[idx] += 1.0
    
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    
    return vec
