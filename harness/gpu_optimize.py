"""
GPU Optimization Module — Swarmind Acceleration Engine.

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
import time

import numpy as np

from harness.common import fallback_embedding
from harness.gpu_accel import DEVICE, HAVE_CUDA

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GPU-Accelerated Embedding
# ---------------------------------------------------------------------------

def gpu_embedding(
    text: str,
    texts: list[str] | None = None,
    dim: int = 384,
) -> np.ndarray:
    """
    Generación de embeddings acelerada por GPU.

    Si se pasa `texts` (batch), procesa todos en paralelo en GPU.
    Si solo `text`, procesa uno.

    El embedding base (hashing Knuth de frecuencias) es DRY con
    `harness.common.fallback_embedding` (estándar del harness): los vectores
    son idénticos en CPU y GPU, garantizando consistencia con los datos
    históricos de LanceDB.

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
        return np.array([fallback_embedding(t, dim) for t in texts])

    # Single mode
    if HAVE_CUDA:
        return _gpu_single_embedding(text, dim)
    return fallback_embedding(text, dim)


def _cpu_embedding(text: str, dim: int = 384) -> np.ndarray:
    """CPU embedding (character frequency, deterministic, vectorizado).

    Delega en common.fallback_embedding (DRY): mismo algoritmo Knuth hash
    que el resto del harness — vectores consistentes con LanceDB.
    """
    return fallback_embedding(text, dim)


def _hash_indices(text: str, dim: int) -> np.ndarray:
    """Indices Knuth hash de los caracteres del texto (vectorizado)."""
    if not text:
        return np.zeros(0, dtype=np.int64)
    chars = np.frombuffer(text.encode("utf-8", errors="replace"), dtype=np.uint8)
    return (chars.astype(np.int64) * 2654435761) % dim


def _gpu_single_embedding(text: str, dim: int = 384) -> np.ndarray:
    """Single embedding on GPU (via torch index_add_, hashing en GPU)."""
    import torch
    if not text:
        return np.zeros(dim, dtype=np.float32)
    indices = torch.from_numpy(_hash_indices(text, dim)).to(DEVICE)
    vec = torch.zeros(dim, dtype=torch.float32, device=DEVICE)
    ones = torch.ones(indices.numel(), dtype=torch.float32, device=DEVICE)
    vec.index_add_(0, indices, ones)
    positions = torch.arange(indices.numel(), device=DEVICE) % 3
    vec.index_add_(0, indices, positions.to(torch.float32) * 0.1)
    norm = torch.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.cpu().numpy()


def _gpu_batch_embedding(texts: list[str], dim: int = 384) -> np.ndarray:
    """
    Batch embedding en GPU: hashing y normalización por filas en GPU.

    Usa torch.index_add_ (suma atómica en GPU) con indices Knuth por texto.
    Resultado numéricamente idéntico a fallback_embedding (atol 1e-5).

    Args:
        texts: Lista de textos.
        dim: Dimensión del embedding.

    Returns:
        Matriz (N, dim) de embeddings normalizados.
    """
    import torch
    N = len(texts)
    batch = torch.zeros((N, dim), dtype=torch.float32, device=DEVICE)
    for j, text in enumerate(texts):
        if not text:
            continue
        indices = torch.from_numpy(_hash_indices(text, dim)).to(DEVICE)
        ones = torch.ones(indices.numel(), dtype=torch.float32, device=DEVICE)
        batch[j].index_add_(0, indices, ones)
        positions = torch.arange(indices.numel(), device=DEVICE) % 3
        batch[j].index_add_(0, indices, positions.to(torch.float32) * 0.1)

    # Normalizar en GPU en paralelo
    norms = torch.norm(batch, dim=1, keepdim=True)
    batch = torch.where(norms > 0, batch / norms, batch)
    return batch.cpu().numpy()


# ---------------------------------------------------------------------------
# GPU-Accelerated Vector Search
# ---------------------------------------------------------------------------

def gpu_similarity_search(
    query: np.ndarray,
    candidates: np.ndarray,
    top_k: int = 5,
    threshold: float = 0.0,
    min_gpu_size: int = 10000,
) -> list[tuple[int, float]]:
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
    use_gpu = HAVE_CUDA and min_gpu_size <= N

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
    messages: list[str],
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
    DIM = 384
    N = 1000

    # Test 1: Cosine similarity batch (GPU vs CPU)
    q = np.random.randn(DIM).astype(np.float32)
    batch = np.random.randn(N, DIM).astype(np.float32)

    t0 = time.perf_counter()
    for _ in range(100):
        _ = gpu_similarity_search(q, batch, top_k=5)
    t_cos = (time.perf_counter() - t0) / 100 * 1000

    # CPU baseline para el mismo search
    q_norm = q / (np.linalg.norm(q) + 1e-12)
    t0 = time.perf_counter()
    for _ in range(100):
        _ = np.argsort(-(batch @ q_norm))[:5]
    t_cpu = (time.perf_counter() - t0) / 100 * 1000

    # Test 2: Batch embedding (vectorizado)
    texts = ["test message " + str(i) for i in range(N)]

    t0 = time.perf_counter()
    _ = batch_embed_messages(texts, DIM)
    t_emb = (time.perf_counter() - t0) * 1000

    return {
        "gpu_available": HAVE_CUDA,
        "device": "cuda:0" if HAVE_CUDA else "cpu",
        "cosine_similarity_1000x_ms": round(t_cos, 2),
        "cpu_baseline_search_ms": round(t_cpu, 2),
        "search_speedup_x": round(t_cpu / t_cos, 2) if t_cos > 0 else 1.0,
        "batch_embed_1000_ms": round(t_emb, 2),
    }
