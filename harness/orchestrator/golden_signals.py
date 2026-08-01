"""
GoldenSignals — Golden Signals LLM para sistemas multi-agente (ADR-0034).

Recolecta y agrega métricas SRE-flavored para agentes LLM:
  - Latencia por percentiles (p50/p95/p99/max/mean) — el promedio esconde el tail.
  - TTFT (time-to-first-token) — latencia percibida de primera respuesta.
  - Cache-read tokens — % de input servido desde cache del provider.
  - Cost per task — input×tarifa + output×tarifa (5x peso) + cache-read al 10%.
  - Failure-spend ratio — tokens gastados en fallos / tokens totales.
  - Throughput — tokens/seg agregados.

Design: Single Responsibility — este módulo solo RECOLECTA y AGREGA.
El export a dashboard lo hace el llamador (TelemetryTracker delegará aquí).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class _RequestSample:
    """Una muestra individual de una llamada LLM."""
    latency_ms: float
    ttft_ms: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    status: str
    level: int
    agent: str
    timestamp: float


class GoldenSignals:
    """
    Recolector de Golden Signals LLM.

    Uso:
        gs = GoldenSignals(cost_input_per_1k=3.0, cost_output_per_1k=15.0)
        gs.record_request(latency_ms=250, ttft_ms=80, input_tokens=1000,
                          output_tokens=500, cache_read_tokens=400)
        gs.snapshot()  # dict JSON-ready para dashboard
    """

    def __init__(
        self,
        *,
        cost_input_per_1k: float = 0.0,
        cost_output_per_1k: float = 0.0,
        cache_read_discount: float = 0.10,
    ) -> None:
        """
        Inicializa el recolector.

        Args:
            cost_input_per_1k: USD por 1K tokens de input (0 = sin costo).
            cost_output_per_1k: USD por 1K tokens de output (0 = sin costo).
            cache_read_discount: fracción de tarifa que se paga por tokens
                servidos desde cache (default 0.10 = 10%, estándar Anthropic).
        """
        self._samples: list[_RequestSample] = []
        self._cost_input_per_1k = float(cost_input_per_1k)
        self._cost_output_per_1k = float(cost_output_per_1k)
        self._cache_read_discount = float(cache_read_discount)

    # ------------------------------------------------------------------
    # Recolección
    # ------------------------------------------------------------------

    def record_request(
        self,
        *,
        latency_ms: float,
        ttft_ms: float,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        status: str = "success",
        level: int = 0,
        agent: str = "",
    ) -> None:
        """Registra una llamada LLM con sus métricas.

        Args:
            latency_ms: latencia total de la llamada en ms.
            ttft_ms: time-to-first-token en ms.
            input_tokens: tokens de input enviados.
            output_tokens: tokens de output generados.
            cache_read_tokens: tokens de input servidos desde cache (0 si no
                hay soporte o si el cache se invalidó silenciosamente).
            status: "success" | "error" | "timeout" | "rate_limited".
            level: nivel de orquestación (para desglose por nivel).
            agent: nombre del agente (para desglose por agente).
        """
        import time

        sample = _RequestSample(
            latency_ms=float(latency_ms),
            ttft_ms=float(ttft_ms),
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            cache_read_tokens=int(cache_read_tokens),
            status=status,
            level=int(level),
            agent=agent,
            timestamp=time.time(),
        )
        self._samples.append(sample)

    # ------------------------------------------------------------------
    # Agregación
    # ------------------------------------------------------------------

    def percentiles(self, key: str = "latency_ms") -> dict:
        """Calcula percentiles por nearest-rank para una métrica.

        Args:
            key: nombre del atributo a agregar ("latency_ms" | "ttft_ms").

        Returns:
            Dict con p50/p95/p99/max/mean/count. Ceros si no hay muestras.
        """
        values = sorted(getattr(s, key) for s in self._samples)
        n = len(values)
        if n == 0:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0,
                    "mean": 0.0, "count": 0}

        def nearest_rank(p: float) -> float:
            idx = max(1, math.ceil(p / 100.0 * n)) - 1
            return float(values[idx])

        return {
            "p50": nearest_rank(50.0),
            "p95": nearest_rank(95.0),
            "p99": nearest_rank(99.0),
            "max": float(values[-1]),
            "mean": float(sum(values) / n),
            "count": n,
        }

    def total_tokens(self) -> int:
        """Total de tokens (input + output) procesados."""
        return sum(s.input_tokens + s.output_tokens for s in self._samples)

    def cost_per_task(self) -> float:
        """Costo total acumulado de todas las requests.

        El output pesa con tarifa completa; el cache-read se descuenta al
        porcentaje configurado (default 10%).
        """
        total = 0.0
        for s in self._samples:
            paid_input = s.input_tokens - s.cache_read_tokens
            cache_input = s.cache_read_tokens
            total += (
                paid_input / 1000.0 * self._cost_input_per_1k
                + cache_input / 1000.0 * self._cost_input_per_1k * self._cache_read_discount
                + s.output_tokens / 1000.0 * self._cost_output_per_1k
            )
        return total

    def avg_cost_per_task(self) -> float:
        """Costo promedio por request (0 si no hay muestras)."""
        if not self._samples:
            return 0.0
        return self.cost_per_task() / len(self._samples)

    def cache_hit_rate(self) -> float:
        """Proporción de input servido desde cache (0..1)."""
        total_input = sum(s.input_tokens for s in self._samples)
        if total_input == 0:
            return 0.0
        total_cached = sum(s.cache_read_tokens for s in self._samples)
        return total_cached / total_input

    def repeated_requests_without_cache(self) -> bool:
        """True si hay 2+ requests con input>0 y cache_read==0 en todas.

        Detección de cache invalidator silencioso: si requests repetidas
        nunca reportan cache-read, la geometría del prompt está rota.
        """
        with_input = [s for s in self._samples if s.input_tokens > 0]
        if len(with_input) < 2:
            return False
        return all(s.cache_read_tokens == 0 for s in with_input)

    def failure_spend_ratio(self) -> float:
        """Proporción de tokens gastados en requests fallidas (0..1)."""
        total = self.total_tokens()
        if total == 0:
            return 0.0
        failed = sum(
            s.input_tokens + s.output_tokens
            for s in self._samples if s.status != "success"
        )
        return failed / total

    def throughput_tokens_per_sec(self) -> float:
        """Tokens por segundo agregados (span de la primera a última muestra)."""
        if len(self._samples) < 2:
            return 0.0
        span = self._samples[-1].timestamp - self._samples[0].timestamp
        if span <= 0:
            return 0.0
        return self.total_tokens() / span

    def errors_count(self) -> int:
        """Cantidad de requests no exitosas."""
        return sum(1 for s in self._samples if s.status != "success")

    def snapshot(self) -> dict:
        """Export JSON-ready con todas las métricas agregadas.

        Returns:
            Dict plano apto para dashboards (TelemetryTracker.export_summary).
        """
        lat = self.percentiles("latency_ms")
        ttft = self.percentiles("ttft_ms")
        return {
            "total_requests": len(self._samples),
            "errors": self.errors_count(),
            "latency_p50": lat["p50"],
            "latency_p95": lat["p95"],
            "latency_p99": lat["p99"],
            "latency_mean": lat["mean"],
            "latency_max": lat["max"],
            "ttft_p50": ttft["p50"],
            "ttft_p95": ttft["p95"],
            "ttft_p99": ttft["p99"],
            "total_tokens": self.total_tokens(),
            "cache_hit_rate": round(self.cache_hit_rate(), 4),
            "cache_invalidation_suspected": self.repeated_requests_without_cache(),
            "cost_per_task": round(self.cost_per_task(), 6),
            "avg_cost_per_task": round(self.avg_cost_per_task(), 6),
            "failure_spend_ratio": round(self.failure_spend_ratio(), 4),
            "throughput_tokens_per_sec": round(self.throughput_tokens_per_sec(), 2),
        }
