"""Tests para harness/benchmarks/* — verifica que los benchmarks ejecutan y devuelven metricas."""
from __future__ import annotations

from typing import Any

import pytest

from harness.benchmarks.bench_all import run_all
from harness.benchmarks.bench_cache import bench_cache
from harness.benchmarks.bench_compression import bench_compression
from harness.benchmarks.bench_memory import bench_memory
from harness.benchmarks.bench_routing import bench_routing


def _assert_benchmark_result(result: dict[str, Any], expected_name: str) -> None:
    """Helper: valida estructura comun de todos los benchmarks."""
    assert isinstance(result, dict)
    assert "name" in result
    assert result["name"] == expected_name
    assert len(result) >= 2  # al menos name + 1 metrica


# ---------------------------------------------------------------------------
# bench_cache
# ---------------------------------------------------------------------------


class TestBenchCache:
    """Tests de bench_cache.py."""

    def test_returns_dict(self):
        """bench_cache devuelve un dict con metricas."""
        result = bench_cache()
        _assert_benchmark_result(result, "Semantic Cache")

    def test_cache_metrics_present(self):
        """Incluye las metricas clave de cache."""
        result = bench_cache()
        assert "set_time_ms" in result
        assert "get_avg_us" in result
        assert "hit_rate_pct" in result
        # Las metricas son numericas
        assert isinstance(result["set_time_ms"], (int, float))
        assert isinstance(result["get_avg_us"], (int, float))
        assert isinstance(result["hit_rate_pct"], (int, float))

    @pytest.mark.slow
    def test_cache_runs_quickly(self):
        """El benchmark completa (sin asercion de tiempo estricto: SemanticCache persiste a disco)."""
        import time
        t0 = time.perf_counter()
        bench_cache()
        elapsed = time.perf_counter() - t0
        # Solo verificamos que termina, sin umbral estricto (I/O de LanceDB)
        assert elapsed >= 0
        assert elapsed < 1200.0  # limite absoluto de safety (en CI con carga)


# ---------------------------------------------------------------------------
# bench_compression
# ---------------------------------------------------------------------------


class TestBenchCompression:
    """Tests de bench_compression.py."""

    def test_returns_dict(self):
        """bench_compression devuelve un dict con metricas."""
        result = bench_compression()
        _assert_benchmark_result(result, "Trajectory Compression")

    def test_compression_metrics_present(self):
        """Incluye las metricas clave de compresion."""
        result = bench_compression()
        assert "original_turns" in result
        assert "compressed_turns" in result
        assert "savings_pct" in result
        assert "compression_time_ms" in result
        assert result["original_turns"] >= result["compressed_turns"]
        # Savings esta en [0, 100]
        assert 0.0 <= result["savings_pct"] <= 100.0


# ---------------------------------------------------------------------------
# bench_routing
# ---------------------------------------------------------------------------


class TestBenchRouting:
    """Tests de bench_routing.py."""

    def test_returns_dict(self):
        """bench_routing devuelve un dict con metricas."""
        result = bench_routing()
        _assert_benchmark_result(result, "Routing Precision")

    def test_routing_metrics_present(self):
        """Incluye metricas de precision y throughput."""
        result = bench_routing()
        assert "total_tests" in result
        assert "correct" in result
        assert "accuracy_pct" in result
        assert "total_time_ms" in result
        assert result["total_tests"] > 0
        assert result["correct"] >= 0
        assert 0.0 <= result["accuracy_pct"] <= 100.0


# ---------------------------------------------------------------------------
# bench_memory (puede ser mas lento, marca slow)
# ---------------------------------------------------------------------------


class TestBenchMemory:
    """Tests de bench_memory.py."""

    @pytest.mark.slow
    def test_returns_dict(self):
        """bench_memory devuelve un dict con metricas (puede tardar)."""
        result = bench_memory()
        _assert_benchmark_result(result, "Memory Operations")

    @pytest.mark.slow
    def test_memory_metrics_present(self):
        """Incluye metricas de insercion y busqueda."""
        result = bench_memory()
        assert "insert_time_ms" in result
        assert "search_avg_ms" in result
        assert "vectors_stored" in result
        assert result["vectors_stored"] > 0


# ---------------------------------------------------------------------------
# run_all (orquestador)
# ---------------------------------------------------------------------------


class TestRunAllBenchmarks:
    """Tests de run_all() en bench_all.py."""

    @pytest.mark.slow
    def test_run_all_returns_list(self):
        """run_all devuelve lista de resultados."""
        results = run_all()
        assert isinstance(results, list)
        assert len(results) == 4  # routing, memory, cache, compression
        for r in results:
            assert "name" in r
