"""Tests para GoldenSignals — Golden Signals LLM (ADR-0034, Idea 1).

Cubre: percentiles p50/p95/p99, cost-per-task con tarifas, cache hit rate,
failure-spend ratio, TTFT y snapshot exportable.
"""

import pytest

from harness.orchestrator.golden_signals import GoldenSignals


class TestPercentiles:
    """Cálculo de percentiles por nearest-rank."""

    def test_empty_returns_zeros(self):
        gs = GoldenSignals()
        p = gs.percentiles("latency_ms")
        assert p["p50"] == 0.0
        assert p["p95"] == 0.0
        assert p["p99"] == 0.0
        assert p["max"] == 0.0

    def test_p50_p95_p99_known_values(self):
        gs = GoldenSignals()
        for lat in [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]:
            gs.record_request(latency_ms=lat, ttft_ms=10, input_tokens=10,
                              output_tokens=10)
        p = gs.percentiles("latency_ms")
        # nearest-rank: p50 = 500, p95 = 1000 (indice ceil(0.95*10)=10 -> 1000)
        assert p["p50"] == 500.0
        assert p["p95"] == 1000.0
        assert p["p99"] == 1000.0
        assert p["max"] == 1000.0

    def test_mean_and_count(self):
        gs = GoldenSignals()
        gs.record_request(latency_ms=100, ttft_ms=5, input_tokens=1, output_tokens=1)
        gs.record_request(latency_ms=300, ttft_ms=5, input_tokens=1, output_tokens=1)
        p = gs.percentiles("latency_ms")
        assert p["mean"] == 200.0
        assert p["count"] == 2


class TestCostPerTask:
    """Costo por tarea con tarifas input/output y cache-read al 10%."""

    def test_cost_ignores_zero_tariffs(self):
        gs = GoldenSignals()
        gs.record_request(latency_ms=10, ttft_ms=1, input_tokens=1000,
                          output_tokens=500)
        assert gs.cost_per_task() == pytest.approx(0.0)

    def test_cost_with_tariffs(self):
        gs = GoldenSignals(cost_input_per_1k=3.0, cost_output_per_1k=15.0)
        gs.record_request(latency_ms=10, ttft_ms=1, input_tokens=1000,
                          output_tokens=1000)
        # input: 1k*3 = 3.0 ; output: 1k*15 = 15.0 ; total 18.0
        assert gs.cost_per_task() == pytest.approx(18.0)

    def test_cache_read_discount(self):
        gs = GoldenSignals(cost_input_per_1k=3.0, cost_output_per_1k=15.0)
        gs.record_request(latency_ms=10, ttft_ms=1, input_tokens=1000,
                          output_tokens=1000, cache_read_tokens=800)
        # input pagado: 200 full (0.6) + 800*0.1*3/1k (0.24) = 0.84; output 15.0
        assert gs.cost_per_task() == pytest.approx(15.84, rel=1e-6)

    def test_average_cost(self):
        gs = GoldenSignals(cost_input_per_1k=3.0, cost_output_per_1k=15.0)
        gs.record_request(latency_ms=10, ttft_ms=1, input_tokens=1000,
                          output_tokens=1000)
        gs.record_request(latency_ms=10, ttft_ms=1, input_tokens=1000,
                          output_tokens=1000)
        assert gs.avg_cost_per_task() == pytest.approx(18.0)


class TestCacheHitRate:
    """Proporción de input servido desde cache del provider."""

    def test_zero_requests(self):
        gs = GoldenSignals()
        assert gs.cache_hit_rate() == 0.0

    def test_partial_hit(self):
        gs = GoldenSignals()
        gs.record_request(latency_ms=10, ttft_ms=1, input_tokens=1000,
                          output_tokens=10, cache_read_tokens=600)
        assert gs.cache_hit_rate() == pytest.approx(0.6)

    def test_zero_cache_read_alerts_silent_invalidation(self):
        gs = GoldenSignals()
        gs.record_request(latency_ms=10, ttft_ms=1, input_tokens=1000,
                          output_tokens=10, cache_read_tokens=0)
        gs.record_request(latency_ms=10, ttft_ms=1, input_tokens=1000,
                          output_tokens=10, cache_read_tokens=0)
        # Dos requests idénticos con 0 cache-read = invalidación silenciosa.
        assert gs.cache_hit_rate() == 0.0
        assert gs.repeated_requests_without_cache() is True


class TestFailureSpend:
    """Ratio de tokens gastados en fallos."""

    def test_no_failures(self):
        gs = GoldenSignals()
        gs.record_request(latency_ms=10, ttft_ms=1, input_tokens=100,
                          output_tokens=50)
        assert gs.failure_spend_ratio() == 0.0

    def test_with_failures(self):
        gs = GoldenSignals()
        gs.record_request(latency_ms=10, ttft_ms=1, input_tokens=100,
                          output_tokens=50)
        gs.record_request(latency_ms=10, ttft_ms=1, input_tokens=100,
                          output_tokens=50, status="error")
        # fallo: 150 tokens de 300 totales
        assert gs.failure_spend_ratio() == pytest.approx(0.5)


class TestTTFT:
    """Time-to-first-token agregado."""

    def test_ttft_percentiles(self):
        gs = GoldenSignals()
        for ttft in [50, 100, 200, 400, 800]:
            gs.record_request(latency_ms=1000, ttft_ms=ttft, input_tokens=10,
                              output_tokens=10)
        p = gs.percentiles("ttft_ms")
        assert p["p50"] == 200.0
        assert p["p95"] == 800.0


class TestSnapshot:
    """Export JSON-ready para dashboards."""

    def test_snapshot_structure(self):
        gs = GoldenSignals(cost_input_per_1k=3.0, cost_output_per_1k=15.0)
        gs.record_request(latency_ms=250, ttft_ms=80, input_tokens=1000,
                          output_tokens=500, cache_read_tokens=400,
                          status="success")
        snap = gs.snapshot()
        assert snap["latency_p50"] == 250.0
        assert snap["ttft_p95"] == 80.0
        assert snap["cache_hit_rate"] == pytest.approx(0.4)
        assert snap["cost_per_task"] > 0.0
        assert snap["failure_spend_ratio"] == 0.0
        assert snap["total_requests"] == 1
        assert "throughput_tokens_per_sec" in snap
