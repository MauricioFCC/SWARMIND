"""Benchmark de estrategias de búsqueda RuscaDB: recall@k vs latencia.

Compara el KNN exacto, binario (RaBitQ + oversample), cuantizado (dos etapas)
y filtrado (ACORN) sobre un corpus sintético determinista. Sirve para **elegir**
`search_adaptive(..., strategy=...)` con datos, no por intuición.

Uso:
    python scripts/bench_ruscadb_search.py --n 256 --dim 32 --queries 20
    python scripts/bench_ruscadb_search.py --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(1, str(ROOT))

from harness.memory_rag.ruscadb_store import RuscaDBStore

N = 256
DIM = 32
QUERIES = 20
TOP_K = 5


def recall_at_k(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> float:
    """Recall@k entre dos listas de resultados (ids del score exacto)."""
    expected_ids = {str(item.get("id")) for item in expected}
    actual_ids = {str(item.get("id")) for item in actual}
    return len(expected_ids & actual_ids) / max(len(expected_ids), 1)


def _timed(fn, *args: Any, **kwargs: Any) -> tuple[list[dict[str, Any]], float]:
    """Ejecuta ``fn`` y devuelve (resultado, milisegundos)."""
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - started) * 1000.0


def run(n: int = N, dim: int = DIM, queries: int = QUERIES, top_k: int = TOP_K) -> dict[str, Any]:
    """Mide exact/binary/quantized/filtered y devuelve el informe."""
    rng = np.random.default_rng(7)
    data = rng.normal(size=(n, dim)).astype(np.float32)
    with tempfile.TemporaryDirectory(prefix="bench-ruscadb-") as tmp:
        store = RuscaDBStore(db_path=str(Path(tmp) / "bench.db"))
        try:
            store.create_collection("bench")
            store.insert(
                "bench", data, [{"i": index} for index in range(n)],
                texts=[f"v{index}" for index in range(n)],
            )
            samples = [data[index] for index in range(queries)]
            exact = [store.search("bench", query, top_k=top_k) for query in samples]
            report: dict[str, Any] = {"n": n, "dim": dim, "top_k": top_k, "strategies": {}}
            report["strategies"]["exact"] = _summarize(
                "exact", [1.0] * queries, [0.0] * queries
            )
            for name, call in (
                ("binary_o1", lambda q: store.search_binary("bench", q, top_k, oversample=1)),
                ("binary_o4", lambda q: store.search_binary("bench", q, top_k, oversample=4)),
                ("quantized", lambda q: store.search_quantized("bench", q, top_k)),
            ):
                recalls, times = _measure(call, samples, exact, top_k)
                report["strategies"][name] = _summarize(name, recalls, times)
            allowed = [
                [item["id"] for item in store.search("bench", query, top_k=top_k * 2)]
                for query in samples
            ]
            recalls, times = _measure(
                lambda q, ids: store.search_filtered("bench", q, ids, top_k),
                samples, exact, top_k, allowed,
            )
            report["strategies"]["filtered"] = _summarize("filtered", recalls, times)
            return report
        finally:
            store.close()


def _measure(call, samples, exact, top_k, allowed=None):
    """Recall y latencia por consulta para una estrategia."""
    recalls, times = [], []
    for index, query in enumerate(samples):
        if allowed is None:
            result, elapsed = _timed(call, query)
        else:
            result, elapsed = _timed(call, query, allowed[index])
        recalls.append(recall_at_k(exact[index], result))
        times.append(elapsed)
    return recalls, times


def _summarize(name: str, recalls: list[float], times: list[float]) -> dict[str, Any]:
    """Resumen estadístico de una estrategia."""
    return {
        "strategy": name,
        "recall_mean": round(float(np.mean(recalls)), 4),
        "p50_ms": round(statistics.median(times), 4),
        "p95_ms": round(sorted(times)[max(0, int(len(times) * 0.95) - 1)], 4),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI del benchmark."""
    parser = argparse.ArgumentParser(description="Benchmark de búsqueda RuscaDB")
    parser.add_argument("--n", type=int, default=N)
    parser.add_argument("--dim", type=int, default=DIM)
    parser.add_argument("--queries", type=int, default=QUERIES)
    parser.add_argument("--top-k", type=int, default=TOP_K)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run(args.n, args.dim, args.queries, args.top_k)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for name, item in report["strategies"].items():
            print(
                f"{name:<12} recall@{args.top_k}={item['recall_mean']:.3f} "
                f"p50={item['p50_ms']:.3f}ms p95={item['p95_ms']:.3f}ms"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
