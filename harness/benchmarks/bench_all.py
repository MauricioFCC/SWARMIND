#!/usr/bin/env python3
"""
Benchmark Suite Completa.

Uso:
    python harness/benchmarks/bench_all.py
    python harness/benchmarks/bench_all.py --routing
    python harness/benchmarks/bench_all.py --json
    python harness/benchmarks/bench_all.py --compare
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
logging.basicConfig(level=logging.WARNING)
BASELINE_FILE = Path(__file__).parent / "baseline.json"


def _print_result(r: Dict[str, Any]):
    name = r.get("name", "?")
    print(f"\n  [{name}]")
    for k, v in r.items():
        if k in ("name", "errors"): continue
        if k == "errors" and isinstance(v, list):
            if v: print(f"    Errors: {len(v)}")
            continue
        print(f"    {k}: {v}")


def run_all() -> List[Dict[str, Any]]:
    from harness.benchmarks.bench_routing import bench_routing
    from harness.benchmarks.bench_memory import bench_memory
    from harness.benchmarks.bench_cache import bench_cache
    from harness.benchmarks.bench_compression import bench_compression
    
    print("=" * 60)
    print("  AGENTIC Benchmark Suite")
    print("  " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("=" * 60)
    
    results = []
    for name, fn in [("1. Routing", bench_routing), ("2. Memory", bench_memory),
                     ("3. Cache", bench_cache), ("4. Compression", bench_compression)]:
        print(f"\n=== {name} ===")
        r = fn()
        _print_result(r)
        results.append(r)
    
    print("\n" + "=" * 60)
    print("  Complete")
    print("=" * 60)
    return results


def compare(results: List[Dict]):
    if not BASELINE_FILE.exists():
        BASELINE_FILE.write_text(json.dumps(results, indent=2))
        print("\n  Baseline saved.")
        return
    baseline = json.loads(BASELINE_FILE.read_text())
    print("\n  === Comparison ===\n")
    for cur in results:
        name = cur.get("name", "?")
        prev = next((b for b in baseline if b.get("name") == name), None)
        if not prev: continue
        for k in cur:
            if k in ("name", "errors"): continue
            cv, pv = cur[k], prev.get(k)
            if isinstance(cv, (int, float)) and isinstance(pv, (int, float)):
                d = cv - pv
                pct = d / max(abs(pv), 1) * 100
                print(f"  {name}.{k}: {cv} ({'+' if d>0 else ''}{d:.1f}, {pct:+.1f}%)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--routing", action="store_true")
    p.add_argument("--memory", action="store_true")
    p.add_argument("--cache", action="store_true")
    p.add_argument("--compression", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--compare", action="store_true")
    args = p.parse_args()
    
    mapping = {
        "routing": (args.routing, lambda: [__import__("harness.benchmarks.bench_routing", fromlist=["bench_routing"]).bench_routing()]),
        "memory": (args.memory, lambda: [__import__("harness.benchmarks.bench_memory", fromlist=["bench_memory"]).bench_memory()]),
        "cache": (args.cache, lambda: [__import__("harness.benchmarks.bench_cache", fromlist=["bench_cache"]).bench_cache()]),
        "compression": (args.compression, lambda: [__import__("harness.benchmarks.bench_compression", fromlist=["bench_compression"]).bench_compression()]),
    }
    
    selected = []
    for key, (flag, fn) in mapping.items():
        if flag:
            selected = fn()
            break
    if not selected:
        selected = run_all()
    
    if args.json:
        print(json.dumps(selected, indent=2))
    if args.compare:
        compare(selected)


if __name__ == "__main__":
    main()
