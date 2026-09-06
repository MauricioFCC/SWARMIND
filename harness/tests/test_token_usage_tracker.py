"""
Tests para TokenUsageTracker — medicion de tokens por agente/llamada.

Cubre (ADR-0041 H2, hallazgo Anthropic 2026):
  - UsageRecord: validacion, total(), summary()
  - AgentUsageSummary: summary()
  - TokenUsageTracker: record, record_from_provider, agregacion por agente,
    total_tokens, top_consumers, cache_hit_ratio, alerts, export,
    buffer circular (max_records) y thread-safety.
"""

from __future__ import annotations

import threading
import time
from dataclasses import FrozenInstanceError

import pytest

from harness.memory_rag.token_usage_tracker import (
    ALERT_THRESHOLD,
    MAX_RECORDS,
    AgentUsageSummary,
    CacheHealth,
    TokenUsageTracker,
    UsageRecord,
)

# ===========================================================================
# Tests: UsageRecord
# ===========================================================================


class TestUsageRecord:
    """Tests unitarios para UsageRecord."""

    def test_total_suma_las_4_metricas(self):
        """total() suma input + output + cache_read + cache_write."""
        rec = UsageRecord(
            agent="builder",
            model="gpt-x",
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=20,
            cache_write_tokens=30,
            timestamp=1000.0,
        )
        assert rec.total() == 200

    def test_total_con_solo_input_output(self):
        """total() funciona con cache en 0 (defaults)."""
        rec = UsageRecord(
            agent="builder", model="gpt-x",
            input_tokens=80, output_tokens=20, timestamp=1000.0,
        )
        assert rec.total() == 100

    def test_usage_record_input_negativo_raise(self):
        """input_tokens negativo lanza ValueError con contexto WHAT/WHY/WHERE."""
        with pytest.raises(ValueError, match="WHAT"):
            UsageRecord(
                agent="a", model="m",
                input_tokens=-1, output_tokens=0, timestamp=1000.0,
            )

    def test_usage_record_output_negativo_raise(self):
        """output_tokens negativo lanza ValueError."""
        with pytest.raises(ValueError, match="WHY"):
            UsageRecord(
                agent="a", model="m",
                input_tokens=0, output_tokens=-5, timestamp=1000.0,
            )

    def test_usage_record_agent_vacio_raise(self):
        """agent vacio (o solo espacios) lanza ValueError."""
        with pytest.raises(ValueError, match="agent"):
            UsageRecord(
                agent="", model="m", input_tokens=1, output_tokens=1,
                timestamp=1000.0,
            )
        with pytest.raises(ValueError):
            UsageRecord(
                agent="   ", model="m", input_tokens=1, output_tokens=1,
                timestamp=1000.0,
            )

    def test_usage_record_frozen(self):
        """UsageRecord es inmutable (frozen dataclass)."""
        rec = UsageRecord(
            agent="a", model="m", input_tokens=1, output_tokens=1,
            timestamp=1000.0,
        )
        with pytest.raises(FrozenInstanceError):
            rec.input_tokens = 999  # type: ignore[misc]

    def test_summary_legible(self):
        """summary() retorna un string con agente y total."""
        rec = UsageRecord(
            agent="builder", model="gpt-x",
            input_tokens=100, output_tokens=50,
            cache_read_tokens=20, cache_write_tokens=30, timestamp=1000.0,
        )
        text = rec.summary()
        assert isinstance(text, str)
        assert "builder" in text
        assert "200" in text


# ===========================================================================
# Tests: AgentUsageSummary
# ===========================================================================


class TestAgentUsageSummary:
    """Tests unitarios para AgentUsageSummary."""

    def test_summary_legible(self):
        """summary() retorna un string con agente, calls y total."""
        summary = AgentUsageSummary(
            agent="builder",
            calls=3,
            total_tokens=600,
            input_tokens=400,
            output_tokens=200,
            cache_hits=1,
            est_inferred=True,
        )
        text = summary.summary()
        assert isinstance(text, str)
        assert "builder" in text
        assert "3" in text
        assert "600" in text

    def test_frozen(self):
        """AgentUsageSummary es inmutable (frozen dataclass)."""
        summary = AgentUsageSummary(
            agent="a", calls=1, total_tokens=10, input_tokens=5,
            output_tokens=5, cache_hits=0, est_inferred=False,
        )
        with pytest.raises(FrozenInstanceError):
            summary.total_tokens = 999  # type: ignore[misc]


# ===========================================================================
# Tests: TokenUsageTracker — registro y agregacion
# ===========================================================================


class TestTokenUsageTrackerRecord:
    """Tests de registro y agregacion por agente."""

    def test_record_agrega_por_agente(self):
        """usage_by_agent agrega calls y tokens correctamente por agente."""
        tracker = TokenUsageTracker()
        tracker.record(UsageRecord("a", "m", 100, 50, timestamp=1000.0))
        tracker.record(UsageRecord("a", "m", 200, 60, timestamp=1001.0))
        tracker.record(UsageRecord("b", "m", 10, 5, timestamp=1002.0))

        by_agent = tracker.usage_by_agent()
        assert set(by_agent) == {"a", "b"}

        sum_a = by_agent["a"]
        assert sum_a.calls == 2
        assert sum_a.input_tokens == 300
        assert sum_a.output_tokens == 110
        assert sum_a.total_tokens == 410

        sum_b = by_agent["b"]
        assert sum_b.calls == 1
        assert sum_b.total_tokens == 15

    def test_total_tokens_global(self):
        """total_tokens suma todos los registros globalmente."""
        tracker = TokenUsageTracker()
        tracker.record(UsageRecord("a", "m", 100, 50, timestamp=1000.0))
        tracker.record(UsageRecord("a", "m", 200, 60, timestamp=1001.0))
        tracker.record(UsageRecord("b", "m", 10, 5, timestamp=1002.0))
        assert tracker.total_tokens() == 425

    def test_total_tokens_cero_sin_registros(self):
        """total_tokens es 0 cuando no hay registros."""
        tracker = TokenUsageTracker()
        assert tracker.total_tokens() == 0

    def test_record_cero_tokens_cuenta_como_call(self):
        """Un registro con 0 tokens cuenta como una llamada del agente."""
        tracker = TokenUsageTracker()
        tracker.record(UsageRecord("a", "m", 0, 0, timestamp=1000.0))
        by_agent = tracker.usage_by_agent()
        assert by_agent["a"].calls == 1
        assert by_agent["a"].total_tokens == 0
        assert tracker.total_tokens() == 0

    def test_usage_by_agent_incluye_cache_hits_y_est_inferred(self):
        """cache_hits cuenta llamadas con cache_read>0; est_inferred con cache."""
        tracker = TokenUsageTracker()
        # directo, sin cache -> est_inferred False
        tracker.record(UsageRecord("a", "m", 10, 5, timestamp=1000.0))
        # via provider con cache_read -> cache_hit y est_inferred True
        tracker.record_from_provider(
            "a", "m", {"prompt_tokens": 100, "completion_tokens": 20, "cached_tokens": 30},
        )
        tracker.record_from_provider(
            "a", "m", {"prompt_tokens": 50, "completion_tokens": 10},
        )

        sum_a = tracker.usage_by_agent()["a"]
        assert sum_a.calls == 3
        assert sum_a.cache_hits == 1
        assert sum_a.est_inferred is True

        # agente sin cache -> est_inferred False
        tracker.record(UsageRecord("b", "m", 10, 5, timestamp=1001.0))
        assert tracker.usage_by_agent()["b"].est_inferred is False

    def test_record_from_provider_mapea_claves(self):
        """prompt_tokens/completion_tokens/cached_tokens -> input/output/cache_read."""
        tracker = TokenUsageTracker()
        tracker.record_from_provider(
            "builder", "gpt-x",
            {"prompt_tokens": 100, "completion_tokens": 20, "cached_tokens": 30},
        )
        sum_builder = tracker.usage_by_agent()["builder"]
        assert sum_builder.input_tokens == 100
        assert sum_builder.output_tokens == 20
        assert sum_builder.cache_hits == 1
        assert sum_builder.total_tokens == 150

    def test_record_from_provider_mapea_cache_write(self):
        """cache_read_input_tokens/cache_creation_input_tokens -> cache_read/cache_write."""
        tracker = TokenUsageTracker()
        tracker.record_from_provider(
            "builder", "gpt-x",
            {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "cache_read_input_tokens": 30,
                "cache_creation_input_tokens": 40,
            },
        )
        sum_builder = tracker.usage_by_agent()["builder"]
        assert sum_builder.cache_hits == 1
        assert sum_builder.total_tokens == 190

    def test_record_from_provider_ignora_claves_desconocidas(self):
        """Claves desconocidas del provider se ignoran sin error."""
        tracker = TokenUsageTracker()
        tracker.record_from_provider(
            "builder", "gpt-x",
            {"prompt_tokens": 10, "completion_tokens": 5, "unexpected_key": 999},
        )
        sum_builder = tracker.usage_by_agent()["builder"]
        assert sum_builder.total_tokens == 15


# ===========================================================================
# Tests: TokenUsageTracker — top_consumers y cache_hit_ratio
# ===========================================================================


class TestTokenUsageTrackerRanking:
    """Tests de ranking (top_consumers) y cache_hit_ratio."""

    def test_top_consumers_ordena_desc(self):
        """top_consumers ordena por total_tokens descendente."""
        tracker = TokenUsageTracker()
        tracker.record(UsageRecord("small", "m", 100, 0, timestamp=1000.0))
        tracker.record(UsageRecord("big", "m", 500, 0, timestamp=1001.0))
        tracker.record(UsageRecord("mid", "m", 250, 0, timestamp=1002.0))

        top = tracker.top_consumers()
        assert [s.agent for s in top] == ["big", "mid", "small"]

    def test_top_consumers_respeta_n(self):
        """top_consumers(n) limita la cantidad de resultados."""
        tracker = TokenUsageTracker()
        tracker.record(UsageRecord("small", "m", 100, 0, timestamp=1000.0))
        tracker.record(UsageRecord("big", "m", 500, 0, timestamp=1001.0))
        tracker.record(UsageRecord("mid", "m", 250, 0, timestamp=1002.0))

        top = tracker.top_consumers(n=2)
        assert len(top) == 2
        assert [s.agent for s in top] == ["big", "mid"]

    def test_top_consumers_vacio(self):
        """top_consumers retorna tuple vacia sin registros."""
        tracker = TokenUsageTracker()
        assert tracker.top_consumers() == ()

    def test_cache_hit_ratio_con_cache(self):
        """cache_hit_ratio = cache_read / (input + cache_read)."""
        tracker = TokenUsageTracker()
        tracker.record(UsageRecord("a", "m", 70, 10, cache_read_tokens=30, timestamp=1000.0))
        assert tracker.cache_hit_ratio("a") == pytest.approx(0.3)
        assert tracker.cache_hit_ratio() == pytest.approx(0.3)

    def test_cache_hit_ratio_por_agente(self):
        """cache_hit_ratio por agente y global con multiples agentes."""
        tracker = TokenUsageTracker()
        tracker.record(UsageRecord("a", "m", 70, 10, cache_read_tokens=30, timestamp=1000.0))
        tracker.record(UsageRecord("b", "m", 100, 5, timestamp=1001.0))
        assert tracker.cache_hit_ratio("a") == pytest.approx(0.3)
        assert tracker.cache_hit_ratio("b") == pytest.approx(0.0)
        # global: 30 / (170 + 30) = 0.15
        assert tracker.cache_hit_ratio() == pytest.approx(0.15)

    def test_cache_hit_ratio_sin_cache(self):
        """Sin cache_read el ratio es 0.0."""
        tracker = TokenUsageTracker()
        tracker.record(UsageRecord("a", "m", 100, 0, timestamp=1000.0))
        assert tracker.cache_hit_ratio("a") == 0.0

    def test_cache_hit_ratio_cero_sin_datos(self):
        """Sin datos el ratio es 0.0."""
        tracker = TokenUsageTracker()
        assert tracker.cache_hit_ratio() == 0.0
        assert tracker.cache_hit_ratio("inexistente") == 0.0


# ===========================================================================
# Tests: TokenUsageTracker — alertas y export
# ===========================================================================


class TestTokenUsageTrackerAlerts:
    """Tests de alertas por presupuesto."""

    def test_alerts_uso_sobre_umbral(self):
        """Uso > ALERT_THRESHOLD del budget genera alerta WHAT+WHY+WHERE."""
        tracker = TokenUsageTracker()
        # budget 1000, umbral 800; uso 900 -> alerta
        tracker.record(UsageRecord("coordinator", "m", 900, 0, timestamp=1000.0))
        alerts = tracker.alerts({"coordinator": 1000})
        assert len(alerts) == 1
        assert "coordinator" in alerts[0]
        assert "WHAT" in alerts[0]
        assert "WHY" in alerts[0]
        assert "WHERE" in alerts[0]

    def test_alerts_uso_bajo_umbral(self):
        """Uso <= ALERT_THRESHOLD del budget no genera alerta."""
        tracker = TokenUsageTracker()
        # budget 1000, umbral 800; uso 700 -> sin alerta
        tracker.record(UsageRecord("guardian", "m", 700, 0, timestamp=1000.0))
        assert tracker.alerts({"guardian": 1000}) == ()

    def test_alerts_uso_exactamente_en_umbral_no_alerta(self):
        """Uso exactamente en el umbral (>= estricto: >) no genera alerta."""
        tracker = TokenUsageTracker()
        # budget 1000, umbral 800; uso exactamente 800 -> sin alerta (estricto >)
        tracker.record(UsageRecord("guardian", "m", 800, 0, timestamp=1000.0))
        assert tracker.alerts({"guardian": 1000}) == ()

    def test_alerts_agente_sin_budget_sin_alerta(self):
        """Agente sin presupuesto declarado no genera alerta."""
        tracker = TokenUsageTracker()
        tracker.record(UsageRecord("free_agent", "m", 999999, 0, timestamp=1000.0))
        assert tracker.alerts({}) == ()
        assert tracker.alerts({"otro": 100}) == ()

    def test_alerts_sin_registros_sin_alerta(self):
        """Sin registros no hay alertas aunque existan budgets."""
        tracker = TokenUsageTracker()
        assert tracker.alerts({"coordinator": 1000}) == ()

    def test_alerts_constante_umbral(self):
        """ALERT_THRESHOLD es 0.8."""
        assert ALERT_THRESHOLD == 0.8


class TestTokenUsageTrackerExport:
    """Tests de export() como snapshot serializable."""

    def test_export_serializable_contiene_total(self):
        """export retorna un dict JSON-serializable con total_tokens."""
        tracker = TokenUsageTracker()
        tracker.record(UsageRecord("a", "m", 100, 50, timestamp=1000.0))
        export = tracker.export()

        assert isinstance(export, dict)
        assert export["total_tokens"] == 150
        assert "agents" in export
        assert export["agents"]["a"]["calls"] == 1
        assert export["agents"]["a"]["input_tokens"] == 100
        assert export["agents"]["a"]["output_tokens"] == 50

    def test_export_es_json_serializable(self):
        """export puede pasar por json.dumps (sin tipos no serializables)."""
        import json

        tracker = TokenUsageTracker()
        tracker.record(UsageRecord("a", "m", 100, 50, timestamp=1000.0))
        payload = json.dumps(tracker.export())
        assert "total_tokens" in payload

    def test_export_vacio(self):
        """export con tracker vacio tiene total_tokens=0 y agents vacio."""
        tracker = TokenUsageTracker()
        export = tracker.export()
        assert export["total_tokens"] == 0
        assert export["agents"] == {}


# ===========================================================================
# Tests: TokenUsageTracker — buffer circular y concurrencia
# ===========================================================================


class TestTokenUsageTrackerCircular:
    """Tests del buffer circular (max_records)."""

    def test_max_records_default(self):
        """MAX_RECORDS es 10000 por defecto."""
        assert MAX_RECORDS == 10000

    def test_max_records_circular_descarta_antiguos(self):
        """Superar max_records descarta los registros mas antiguos."""
        tracker = TokenUsageTracker(max_records=3)
        for i in range(5):
            tracker.record(UsageRecord("a", "m", 10, 0, timestamp=float(i)))

        # Solo los ultimos 3 registros sobreviven: 10*3 = 30
        assert tracker.total_tokens() == 30
        assert tracker.usage_by_agent()["a"].calls == 3

    def test_max_records_circular_con_multiples_agentes(self):
        """El descarte aplica por antiguedad global, no por agente."""
        tracker = TokenUsageTracker(max_records=2)
        tracker.record(UsageRecord("a", "m", 10, 0, timestamp=0.0))
        tracker.record(UsageRecord("b", "m", 20, 0, timestamp=1.0))
        tracker.record(UsageRecord("a", "m", 30, 0, timestamp=2.0))

        by_agent = tracker.usage_by_agent()
        # Se descarto el registro mas antiguo (a: 10)
        assert by_agent["a"].total_tokens == 30
        assert by_agent["b"].total_tokens == 20
        assert tracker.total_tokens() == 50

    def test_init_valida_max_records(self):
        """max_records < 1 lanza ValueError."""
        with pytest.raises(ValueError):
            TokenUsageTracker(max_records=0)


class TestTokenUsageTrackerThreadSafety:
    """Verifica que el tracker es seguro bajo concurrencia."""

    def test_thread_safety_50_records_2_hilos(self):
        """50 records desde 2 hilos: total_tokens correcto sin carrera."""
        tracker = TokenUsageTracker(max_records=100)
        errors: list[Exception] = []

        def worker() -> None:
            try:
                for _ in range(25):
                    tracker.record(
                        UsageRecord("t", "m", 2, 1, timestamp=time.time())
                    )
            except ValueError as exc:  # pragma: no cover - solo en fallo
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert tracker.total_tokens() == 150  # 50 llamadas * 3 tokens
        assert tracker.usage_by_agent()["t"].calls == 50

    def test_thread_safety_lecturas_concurrentes(self):
        """Lecturas (usage_by_agent) concurrentes con escrituras no rompen."""
        tracker = TokenUsageTracker(max_records=100)
        stop = threading.Event()

        def writer() -> None:
            for i in range(50):
                tracker.record(
                    UsageRecord("w", "m", 1, 0, timestamp=float(i))
                )
            stop.set()

        def reader() -> None:
            while not stop.is_set():
                tracker.usage_by_agent()
                tracker.total_tokens()

        w = threading.Thread(target=writer)
        r = threading.Thread(target=reader)
        w.start()
        r.start()
        w.join()
        r.join()

        assert tracker.total_tokens() == 50


# ===========================================================================
# Tests: cache_health (frontera 2026: hit<60% con volumen = bug estructural)
# ===========================================================================


class TestCacheHealth:
    """Salud de cache de prompt por agente."""

    def _tracker_with(
        self, agent: str, inputs: int, reads: int, calls: int = 10
    ) -> TokenUsageTracker:
        """Tracker con N llamadas repartiendo inputs/reads."""
        tracker = TokenUsageTracker()
        for i in range(calls):
            tracker.record(UsageRecord(
                agent, "m",
                inputs // calls, 0,
                cache_read_tokens=reads // calls,
                timestamp=float(i),
            ))
        return tracker

    def test_healthy_high_hit_ratio(self) -> None:
        """Hit ratio alto no levanta alerta."""
        tracker = self._tracker_with("a", 20000, 32000)
        (health,) = tracker.cache_health(min_input_tokens=10000)
        assert health.agent == "a"
        assert health.hit_ratio == pytest.approx(32000 / 52000)
        assert health.needs_attention is False

    def test_low_hit_ratio_with_volume_flags_structural_bug(self) -> None:
        """Hit <60% con volumen suficiente marca bug estructural."""
        tracker = self._tracker_with("b", 20000, 1000)
        (health,) = tracker.cache_health(min_input_tokens=10000)
        assert health.needs_attention is True
        assert "cache-buster" in health.reason

    def test_low_volume_no_flag(self) -> None:
        """Poco volumen no marca aunque el ratio sea bajo."""
        tracker = self._tracker_with("c", 500, 10)
        (health,) = tracker.cache_health(min_input_tokens=10000)
        assert health.needs_attention is False

    def test_empty_tracker_empty(self) -> None:
        """Sin registros retorna tupla vacia."""
        assert TokenUsageTracker().cache_health() == ()

    def test_health_is_frozen(self) -> None:
        """CacheHealth es inmutable."""
        tracker = self._tracker_with("d", 20000, 32000)
        (health,) = tracker.cache_health(min_input_tokens=10000)
        assert isinstance(health, CacheHealth)
        with pytest.raises(FrozenInstanceError):
            health.hit_ratio = 0.5  # type: ignore[misc]
