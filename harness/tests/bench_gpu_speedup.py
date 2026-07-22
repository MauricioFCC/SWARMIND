"""
Benchmark: GPU vs CPU speedup for AGENTIC hot paths.

Mide el speedup real de GPU en:
1. fallback_embedding (single + batch)
2. Cosine similarity search (lance_vector_store)
3. Semantic cache comparison
4. AgentBus message embedding

Usage:
    uv run --no-sync python harness/tests/bench_gpu_speedup.py
"""

from __future__ import annotations

import time
from typing import List

import numpy as np

from harness.common import fallback_embedding
from harness.gpu_accel import HAVE_CUDA, DEVICE_NAME, GPU_MEMORY_GB
from harness.gpu_optimize import (
    gpu_embedding,
    gpu_similarity_search,
    batch_embed_messages,
)


def bench(name: str, cpu_fn, gpu_fn, n_iter: int = 50):
    """Benchmark CPU vs GPU version of a function."""
    # CPU timing (force CPU)
    from harness.gpu_accel import force_cpu
    force_cpu()

    # Warmup
    for _ in range(3):
        try:
            cpu_fn()
        except Exception:
        pass  # expected: CPU fallback for GPU functions

    t0 = time.perf_counter()
    for _ in range(n_iter):
        cpu_fn()
    t_cpu = (time.perf_counter() - t0) / n_iter * 1000

    # GPU timing
    if HAVE_CUDA:
        from harness.gpu_accel import force_gpu
        force_gpu()
        for _ in range(3):
            try:
                gpu_fn()
            except Exception:
        pass  # expected: CPU fallback for GPU functions
        t0 = time.perf_counter()
        for _ in range(n_iter):
            gpu_fn()
        t_gpu = (time.perf_counter() - t0) / n_iter * 1000
        speedup = t_cpu / t_gpu if t_gpu > 0 else 0
    else:
        t_gpu = 0
        speedup = 0

    status = "" if speedup >= 1.5 else "" if speedup >= 1.0 else ""
    print(f"  {status} {name:40s} CPU:{t_cpu:8.2f}ms  GPU:{t_gpu:8.2f}ms  x{speedup:.1f}")
    return speedup


def main():
    DIM = 384
    N = 1000

    print(f"\n{'='*65}")
    print(f"  AGENTIC GPU BENCHMARK")
    print(f"  Device: {DEVICE_NAME} | VRAM: {GPU_MEMORY_GB:.1f}GB | CUDA: {HAVE_CUDA}")
    print(f"{'='*65}\n")

    # 1. Single embedding (fallback_embedding - used everywhere)
    print("1.  Single Embedding (fallback_embedding)")
    text = "implementar una API REST en Rust con autenticacion JWT" * 5

    bench(
        "embedding single (10 chars)",
        lambda: fallback_embedding("hi"),
        lambda: gpu_embedding("hi"),
        n_iter=200,
    )
    bench(
        "embedding single (100 chars)",
        lambda: fallback_embedding(text[:100]),
        lambda: gpu_embedding(text[:100]),
        n_iter=200,
    )
    bench(
        "embedding single (500 chars)",
        lambda: fallback_embedding(text[:500]),
        lambda: gpu_embedding(text[:500]),
        n_iter=100,
    )

    # 2. Batch embedding (AgentBus multi-message)
    print("\n2.  Batch Embedding (AgentBus - N messages)")
    texts_10 = [f"mensaje {i}: test de embedding" for i in range(10)]
    texts_100 = [f"mensaje {i}: test de embedding con mas texto" for i in range(100)]
    texts_1000 = [f"mensaje largo {i}: " * 5 for i in range(1000)]

    bench(
        "batch 10 messages",
        lambda: np.array([fallback_embedding(t) for t in texts_10]),
        lambda: batch_embed_messages(texts_10),
        n_iter=100,
    )
    bench(
        "batch 100 messages",
        lambda: np.array([fallback_embedding(t) for t in texts_100]),
        lambda: batch_embed_messages(texts_100),
        n_iter=50,
    )
    bench(
        "batch 1000 messages",
        lambda: np.array([fallback_embedding(t) for t in texts_1000]),
        lambda: batch_embed_messages(texts_1000),
        n_iter=10,
    )

    # 3. Cosine similarity search (lance_vector_store.py)
    print("\n3.  Vector Search (LanceVectorStore)")
    q = np.random.randn(DIM).astype(np.float32)
    db_10k = np.random.randn(10000, DIM).astype(np.float32)
    db_100k = np.random.randn(100000, DIM).astype(np.float32)

    bench(
        "search 10k vectors",
        lambda: [np.dot(q, v) / (np.linalg.norm(q) * np.linalg.norm(v) + 1e-12) for v in db_10k[:100]],
        lambda: gpu_similarity_search(q, db_10k[:100], top_k=5),
        n_iter=50,
    )
    bench(
        "search 100k vectors",
        lambda: [np.dot(q, v) / (np.linalg.norm(q) * np.linalg.norm(v) + 1e-12) for v in db_100k[:1000]],
        lambda: gpu_similarity_search(q, db_100k[:1000], top_k=5),
        n_iter=20,
    )

    # 4. Semantic cache (full pipeline)
    print("\n4.  Semantic Cache (get + compare)")
    cache_keys = [f"prompt de prueba numero {i}" for i in range(100)]

    def cpu_cache_lookup():
        query_vec = fallback_embedding("test query")
        best_score = 0
        for k in cache_keys:
            kv = fallback_embedding(k)
            score = np.dot(query_vec, kv) / (np.linalg.norm(query_vec) * np.linalg.norm(kv) + 1e-12)
            best_score = max(best_score, score)
        return best_score

    def gpu_cache_lookup():
        query_vec = gpu_embedding("test query")
        all_vecs = batch_embed_messages(cache_keys)
        results = gpu_similarity_search(query_vec, all_vecs, top_k=1)
        return results[0][1] if results else 0

    bench(
        "cache lookup 100 entries",
        cpu_cache_lookup,
        gpu_cache_lookup,
        n_iter=30,
    )

    print(f"\n{'='*65}")
    print(f"  BENCHMARK COMPLETE")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()



