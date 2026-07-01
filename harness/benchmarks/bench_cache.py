"""Benchmark: Semantic Cache."""
from __future__ import annotations
import time
from typing import Any, Dict
from harness.memory_rag.semantic_cache import SemanticCache


def bench_cache() -> Dict[str, Any]:
    cache = SemanticCache(threshold=0.5)
    n = 50
    t0 = time.perf_counter()
    for i in range(n):
        cache.set(f"test prompt {i}", f"response_{i}", agent_role="test")
    t_set = time.perf_counter() - t0
    
    hits = 0
    n_get = 100
    t0 = time.perf_counter()
    for i in range(n_get):
        r = cache.get(f"test prompt {i % n}", agent_role="test")
        if r: hits += 1
    t_get = time.perf_counter() - t0
    
    return {
        "name": "Semantic Cache",
        "set_time_ms": round(t_set * 1000, 2),
        "set_throughput": round(n / t_set, 1) if t_set > 0 else 0,
        "get_avg_us": round(t_get / n_get * 1_000_000, 1),
        "get_throughput": round(n_get / t_get, 1) if t_get > 0 else 0,
        "hit_rate_pct": round(hits / n_get * 100, 1),
    }
