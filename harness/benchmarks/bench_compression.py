"""Benchmark: Trajectory Compression."""
from __future__ import annotations

import time
from typing import Any, Dict, List

from harness.memory_rag.trajectory_compressor import TrajectoryCompressor


def _gen_conv(n: int) -> List[Dict]:
    conv = []
    for i in range(n):
        txt = f"Turn {i}: " + "lorem ipsum dolor sit amet " * 10
        conv.append({"role": "user" if i % 2 == 0 else "assistant", "content": txt})
    return conv


def bench_compression() -> Dict[str, Any]:
    comp = TrajectoryCompressor(min_tokens=100)
    conv = _gen_conv(30)
    orig_tok = sum(max(1, len(m["content"]) // 4) for m in conv)

    t0 = time.perf_counter()
    compressed = comp.compress(conv)
    t_comp = time.perf_counter() - t0

    comp_tok = sum(max(1, len(m["content"]) // 4) for m in compressed)
    savings = (orig_tok - comp_tok) / max(orig_tok, 1) * 100

    return {
        "name": "Trajectory Compression",
        "original_turns": len(conv),
        "compressed_turns": len(compressed),
        "original_tokens": orig_tok,
        "compressed_tokens": comp_tok,
        "savings_pct": round(savings, 1),
        "compression_time_ms": round(t_comp * 1000, 2),
    }
