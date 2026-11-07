"""Tests del KernelBus determinista del orchestrator (AC-KN1..AC-KN4)."""

from __future__ import annotations

import pytest

from harness.orchestrator.agent_bus import KernelBus, KernelBusError


class TestKernelBusDeterminism:
    """Dispatch FIFO, orden canónico y replay."""

    def test_publish_dispatches_in_fifo_order(self):
        """Los suscriptores ven los eventos en el orden de publicación."""
        bus = KernelBus()
        seen: list[int] = []
        bus.subscribe("task", lambda payload, _env: seen.append(payload["n"]))
        for n in (1, 2, 3):
            bus.publish("task", {"n": n})
        assert seen == [1, 2, 3]
        assert bus.pending() == 0

    def test_drain_false_batches_messages(self):
        """publish(drain=False) acumula y drain() procesa el lote completo."""
        bus = KernelBus()
        processed: list[int] = []
        bus.subscribe("task", lambda payload, _env: processed.append(payload["n"]))
        bus.publish("task", {"n": 1}, drain=False)
        bus.publish("task", {"n": 2}, drain=False)
        assert processed == []
        assert bus.pending() == 2
        assert bus.drain() == 2
        assert processed == [1, 2]

    def test_seq_is_monotonic_and_trace_id_propagates(self):
        """El envelope lleva seq monotónica y el trace_id de correlación."""
        bus = KernelBus()
        seen: list[tuple[int, str]] = []
        bus.subscribe("task", lambda _payload, env: seen.append((env.seq, env.trace_id)))
        bus.publish("task", {}, trace_id="trace-1")
        bus.publish("task", {}, trace_id="trace-1", source="test")
        assert seen == [(1, "trace-1"), (2, "trace-1")]
        replay = bus.replay()
        assert [entry["seq"] for entry in replay] == [1, 2]
        assert replay[1]["source"] == "test"

    def test_replay_is_serializable(self):
        """replay() devuelve dicts con el payload deserializado."""
        bus = KernelBus()
        bus.subscribe("task", lambda _payload, _env: None)
        bus.publish("task", {"n": 7})
        assert bus.replay()[0]["payload"] == {"n": 7}

    def test_stats_count_by_kind(self):
        """stats expone dispatch por tipo de evento."""
        bus = KernelBus()
        bus.subscribe("a", lambda _payload, _env: None)
        bus.publish("a")
        bus.publish("a")
        assert bus.stats.by_kind == {"a": 2}
        assert bus.stats.dispatched == 2


class TestKernelBusBackpressure:
    """Cola acotada: backpressure explícito, nunca descarte silencioso."""

    def test_full_mailbox_raises_typed_error_and_does_not_log(self):
        """Un publish rechazado no consume seq ni queda en el event log."""
        bus = KernelBus(capacity=1)
        bus.subscribe("task", lambda _payload, _env: None)
        bus.publish("task", {"n": 1}, drain=False)
        with pytest.raises(KernelBusError) as excinfo:
            bus.publish("task", {"n": 2}, drain=False)
        assert "backpressure" in str(excinfo.value)
        assert len(bus.replay()) == 1
        assert bus.pending() == 1

    def test_unregistered_kind_is_logged_but_does_not_stop(self):
        """Sin fail_fast, un kind sin suscriptor se registra y sigue."""
        bus = KernelBus()
        bus.publish("nadie")
        assert bus.stats.unregistered == 1
        assert [entry["kind"] for entry in bus.replay()] == [
            "nadie",
            "kernel.unregistered",
        ]

    def test_fail_fast_wraps_handler_error(self):
        """Con fail_fast, el fallo del handler sale como KernelBusError."""
        bus = KernelBus(fail_fast=True)

        def _boom(_payload, _env):
            raise RuntimeError("explota")

        bus.subscribe("boom", _boom)
        with pytest.raises(KernelBusError) as excinfo:
            bus.publish("boom")
        assert "fail_fast" in str(excinfo.value)
        assert bus.fail_fast is True

    def test_subscribe_rejects_non_callable(self):
        """Un handler no invocable es error de programación."""
        bus = KernelBus()
        with pytest.raises(KernelBusError):
            bus.subscribe("task", 42)  # type: ignore[arg-type]
