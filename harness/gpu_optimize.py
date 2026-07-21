"""
GPU Optimization Module — AGENTIC Acceleration Engine.

Integra GPU acceleration en los puntos críticos del sistema multi-agente:

1. fallback_embedding() → gpu_embedding() batch en GPU
2. LanceVectorStore.search() → distancia coseno en GPU
3. SemanticCache.get() → comparación batch en GPU
4. AgentBus.post_message() → embeddings paralelos

Uso:
    from harness.gpu_optimize import gpu_embedding, gpu_search
    vec = gpu_embedding("texto a embedder")        # GPU si disponible
    results = gpu_search(query_vec, all_vectors)   # GPU batch
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

import numpy as np

from harness.gpu_accel import HAVE_CUDA, DEVICE, to_gpu, to_cpu

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GPU-Accelerated Embedding
# ---------------------------------------------------------------------------

def gpu_embedding(
    text: str,
    texts: Optional[List[str]] = None,
    dim: int = 384,
) -> np.ndarray:
    """
    Generación de embeddings acelerada por GPU.

    Si se pasa `texts` (batch), procesa todos en paralelo en GPU.
    Si solo `text`, procesa uno.

    Args:
        text: Texto único a embedder.
        texts: Lista opcional de textos para batch processing.
        dim: Dimensión del embedding (default: 384).

    Returns:
        Vector de embedding (1D si text, 2D si texts).
    """
    if texts:
        # Batch mode: procesar todos los textos en GPU
        if HAVE_CUDA:
            return _gpu_batch_embedding(texts, dim)
        return np.array([_cpu_embedding(t, dim) for t in texts])

    # Single mode
    if HAVE_CUDA:
        return _gpu_single_embedding(text, dim)
    return _cpu_embedding(text, dim)


def _cpu_embedding(text: str, dim: int = 384) -> np.ndarray:
    """CPU embedding (character frequency, deterministic)."""
    if not text:
        return np.zeros(dim, dtype=np.float32)
    vec = np.zeros(dim, dtype=np.float32)
    for i, ch in enumerate(text):
        idx = (ord(ch) * 2654435761) % dim
        vec[idx] += 1.0 + (i % 3) * 0.1
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def _gpu_single_embedding(text: str, dim: int = 384) -> np.ndarray:
    """Single embedding on GPU (via torch)."""
    import torch
    if not text:
        return np.zeros(dim, dtype=np.float32)
    vec = torch.zeros(dim, dtype=torch.float32, device=DEVICE)
    for i, ch in enumerate(text):
        idx = (ord(ch) * 2654435761) % dim
        vec[idx] += 1.0 + (i % 3) * 0.1
    norm = torch.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.cpu().numpy()


def _gpu_batch_embedding(texts: List[str], dim: int = 384) -> np.ndarray:
    """
    Batch embedding en GPU: procesa N textos simultáneamente.

    Construye una matriz de frecuencias de caracteres en CPU, luego
    normaliza por filas en GPU en paralelo.

    Args:
        texts: Lista de textos.
        dim: Dimensión del embedding.

    Returns:
        Matriz (N, dim) de embeddings.
    """
    import torch
    N = len(texts)
    batch = np.zeros((N, dim), dtype=np.float32)

    for j, text in enumerate(texts):
        if not text:
            continue
        for i, ch in enumerate(text):
            idx = (ord(ch) * 2654435761) % dim
            batch[j, idx] += 1.0 + (i % 3) * 0.1

    # Normalizar en GPU en paralelo
    t_batch = torch.from_numpy(batch).to(DEVICE)
    norms = torch.norm(t_batch, dim=1, keepdim=True)
    t_batch = torch.where(norms > 0, t_batch / norms, t_batch)
    return t_batch.cpu().numpy()


# ---------------------------------------------------------------------------
# GPU-Accelerated Vector Search
# ---------------------------------------------------------------------------

def gpu_similarity_search(
    query: np.ndarray,
    candidates: np.ndarray,
    top_k: int = 5,
    threshold: float = 0.0,
    min_gpu_size: int = 10000,
) -> List[Tuple[int, float]]:
    """
    Búsqueda por similitud coseno con enrutamiento inteligente CPU/GPU.

    Usa GPU para batches grandes (>min_gpu_size) y CPU para batches pequeños.
    El punto de equilibrio está en ~10k vectores donde GPU empieza a ganar.

    Args:
        query: Vector query (1D).
        candidates: Matriz de candidatos (N x D).
        top_k: Número de resultados a retornar.
        threshold: Umbral mínimo de similitud.
        min_gpu_size: Mínimo de vectores para usar GPU (default: 10000).

    Returns:
        Lista de (índice, similitud) ordenada por similitud descendente.
    """
    if query.ndim == 1:
        query = query.reshape(1, -1)

    N = candidates.shape[0]

    # Smart routing: GPU solo para batches grandes
    use_gpu = HAVE_CUDA and N >= min_gpu_size

    if use_gpu:
        import torch
        tq = torch.from_numpy(query).to(DEVICE)
        tc = torch.from_numpy(candidates).to(DEVICE)
        scores = torch.nn.functional.cosine_similarity(tq, tc)
        scores_np = np.asarray(scores.cpu().numpy())
    else:
        q_norm = np.linalg.norm(query)
        c_norms = np.linalg.norm(candidates, axis=1)
        denom = c_norms * q_norm + 1e-12
        scores_np = np.asarray(np.dot(candidates, query.flatten()) / denom)

    # Filtrar por threshold y tomar top_k
    if threshold > 0:
        valid = np.where(scores_np >= threshold)[0]
        if len(valid) == 0:
            return []
        indices = valid[np.argsort(-scores_np[valid])[:top_k]]
    else:
        indices = np.argsort(-scores_np)[:top_k]

    return [(int(idx), float(scores_np[idx])) for idx in indices]


# ---------------------------------------------------------------------------
# GPU-Accelerated Batch Processing for AgentBus
# ---------------------------------------------------------------------------

def batch_embed_messages(
    messages: List[str],
    dim: int = 384,
) -> np.ndarray:
    """
    Generar embeddings para múltiples mensajes en batch (GPU si disponible).

    Diseñado para AgentBus.post_message() donde se embeddean N mensajes
    simultáneamente.

    Args:
        messages: Lista de mensajes.
        dim: Dimensión del embedding.

    Returns:
        Matriz (N, dim) de embeddings.
    """
    return gpu_embedding("", texts=messages, dim=dim)


def gpu_self_test() -> dict:
    """
    Ejecutar autodiagnóstico GPU y retornar métricas de rendimiento.

    Returns:
        Dict con métricas: device, vector_ops_ms, embedding_ms, speedup.
    """
    import time

    DIM = 384
    N = 1000

    # Test 1: Cosine similarity batch
    q = np.random.randn(DIM).astype(np.float32)
    batch = np.random.randn(N, DIM).astype(np.float32)

    t0 = time.perf_counter()
    for _ in range(100):
        _ = gpu_similarity_search(q, batch, top_k=5)
    t_cos = (time.perf_counter() - t0) / 100 * 1000

    # Test 2: Batch embedding
    texts = ["test message " + str(i) for i in range(N)]

    t0 = time.perf_counter()
    _ = batch_embed_messages(texts, DIM)
    t_emb = (time.perf_counter() - t0) * 1000

    return {
        "gpu_available": HAVE_CUDA,
        "device": "cuda:0" if HAVE_CUDA else "cpu",
        "cosine_similarity_1000x_ms": round(t_cos, 2),
        "batch_embed_1000_ms": round(t_emb, 2),
    }
