"""Benchmark: Memoria y RAG."""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from harness.memory_rag.lance_vector_store import LanceVectorStore


def bench_memory() -> dict[str, Any]:
    # Usar db_path temporal para forzar modo in-memory (evita schema conflicts con tablas LanceDB existentes)
    import tempfile
    from pathlib import Path
    tmpdir = tempfile.mkdtemp()
    store = LanceVectorStore(db_path=str(Path(tmpdir) / "bench.lancedb"), allow_fallback=True)
    n = 100
    dim = 384
    vectors = np.random.randn(n, dim).astype(np.float32)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    metadata = [{"source_file": f"doc_{i}.py", "start_line": 0, "end_line": 10, "domain": "test", "tipo_doc": "code", "tags": ["t"]} for i in range(n)]

    t0 = time.perf_counter()
    store.insert("rag_chunks", vectors, metadata)
    t_insert = time.perf_counter() - t0

    n_q = 20
    t0 = time.perf_counter()
    for _ in range(n_q):
        store.search("rag_chunks", vectors[0], top_k=5)
    t_search = time.perf_counter() - t0

    # Cleanup temp dir
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    return {
        "name": "Memory Operations",
        "insert_time_ms": round(t_insert * 1000, 2),
        "insert_throughput": round(n / t_insert, 1) if t_insert > 0 else 0,
        "search_avg_ms": round(t_search / n_q * 1000, 2),
        "search_qps": round(n_q / t_search, 1) if t_search > 0 else 0,
        "vectors_stored": n,
    }
