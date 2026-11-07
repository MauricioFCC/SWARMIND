"""Tests del kernel event-driven de SWARMIND (mensajes, mailbox, event log)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import MappingProxyType

import pytest

from harness.kernel import (
    BoundedMailbox,
    EventLog,
    EventLogFullError,
    KernelLoop,
    MailboxFullError,
    MessageEnvelope,
    UnregisteredKindError,
)


def _raiser(_payload, _envelope) -> None:
    """Handler que falla siempre (para la política de errores del loop)."""
    raise RuntimeError("boom")



class TestMessageEnvelope:
    """Inmutabilidad y validación del sobre."""

    def test_payload_is_frozen(self):
        """El payload no puede mutarse tras crear el envelope."""
        envelope = MessageEnvelope(seq=1, kind="task", payload={"a": 1})
        with pytest.raises(TypeError):
            envelope.payload["a"] = 2  # type: ignore[index]

    def test_payload_is_copied(self):
        """Mutar el dict original no afecta al envelope."""
        original = {"a": 1}
        envelope = MessageEnvelope(seq=1, kind="task", payload=original)
        original["a"] = 99
        assert envelope.payload["a"] == 1

    def test_rejects_empty_kind(self):
        """kind vacío es error de programación."""
        with pytest.raises(ValueError):
            MessageEnvelope(seq=1, kind="  ")

    def test_rejects_non_mapping_payload(self):
        """payload debe ser Mapping."""
        with pytest.raises(TypeError):
            MessageEnvelope(seq=1, kind="task", payload=[1, 2])  # type: ignore[arg-type]

    def test_created_at_is_utc_aware(self):
        """created_at usa UTC (`dt.UTC`), nunca horario local sin zona."""
        envelope = MessageEnvelope(seq=1, kind="task")
        created = datetime.fromisoformat(envelope.created_at)
        assert created.tzinfo is not None
        assert created.utcoffset() == timedelta(0)

    def test_kind_validation_message_is_actionable(self):
        """El ValueError identifica el campo y acepta cadena vacía y no-str."""
        with pytest.raises(ValueError, match="kind vacio o no-str"):
            MessageEnvelope(seq=1, kind="")
        with pytest.raises(ValueError, match="kind vacio o no-str"):
            MessageEnvelope(seq=1, kind=42)  # type: ignore[arg-type]

    def test_as_dict_contract(self):
        """as_dict devuelve exactamente los 6 campos con sus valores."""
        envelope = MessageEnvelope(
            seq=7,
            kind="task",
            payload={"n": 1},
            trace_id="t-1",
            source="agente",
            created_at="2026-01-02T03:04:05+00:00",
        )
        assert envelope.as_dict() == {
            "seq": 7,
            "kind": "task",
            "payload": {"n": 1},
            "trace_id": "t-1",
            "source": "agente",
            "created_at": "2026-01-02T03:04:05+00:00",
        }


class TestBoundedMailbox:
    """Cola acotada con backpressure tipado."""

    def test_fifo_order(self):
        """get() devuelve en orden FIFO."""
        box = BoundedMailbox(capacity=4)
        for seq in range(1, 4):
            box.put(MessageEnvelope(seq=seq, kind="k"))
        assert [box.get().seq for _ in range(3)] == [1, 2, 3]
        assert box.get() is None

    def test_full_raises_typed_error(self):
        """Cola llena -> MailboxFullError (nunca descarta)."""
        box = BoundedMailbox(capacity=1)
        box.put(MessageEnvelope(seq=1, kind="k"))
        with pytest.raises(MailboxFullError) as excinfo:
            box.put(MessageEnvelope(seq=2, kind="k"))
        assert "cola_llena" in str(excinfo.value)
        assert box.rejected == 1
        assert len(box) == 1

    def test_invalid_capacity(self):
        """capacity <= 0 es error."""
        with pytest.raises(ValueError):
            BoundedMailbox(capacity=0)

    def test_drain_preserves_order_and_empties(self):
        """drain() devuelve todo en orden y vacía el buzón."""
        box = BoundedMailbox(capacity=8)
        for seq in range(1, 5):
            box.put(MessageEnvelope(seq=seq, kind="k"))
        drained = box.drain()
        assert [item.seq for item in drained] == [1, 2, 3, 4]
        assert len(box) == 0

    def test_default_capacity_and_rejected_counter(self):
        """Los defaults documentados: capacidad 256 y cero rechazos."""
        box = BoundedMailbox()
        assert box.capacity == 256
        assert box.rejected == 0

    def test_rejected_counter_accumulates(self):
        """Cada backpressure suma (no reemplaza) el contador de rechazos."""
        box = BoundedMailbox(capacity=1)
        box.put(MessageEnvelope(seq=1, kind="k"))
        for _ in range(3):
            with pytest.raises(MailboxFullError, match="cola_llena"):
                box.put(MessageEnvelope(seq=2, kind="k"))
        assert box.rejected == 3
        assert len(box) == 1


class TestEventLog:
    """Registro append-only con secuencia monotónica."""

    def test_seq_is_monotonic(self):
        """Cada append incrementa seq en 1."""
        log = EventLog()
        first = log.append("a")
        second = log.append("b")
        assert (first.seq, second.seq) == (1, 2)
        assert log.next_seq == 3

    def test_overflow_raise_is_fail_stop(self):
        """overflow='raise' falla rápido al llenarse (no descarta)."""
        log = EventLog(max_entries=1)
        log.append("a")
        with pytest.raises(EventLogFullError):
            log.append("b")

    def test_overflow_drop_oldest_keeps_window(self):
        """overflow='drop_oldest' mantiene la ventana más reciente."""
        log = EventLog(max_entries=2, overflow="drop_oldest")
        for kind in ("a", "b", "c"):
            log.append(kind)
        assert [entry.kind for entry in log.entries()] == ["b", "c"]

    def test_replay_is_serializable(self):
        """replay() devuelve dicts con payload deserializado."""
        log = EventLog()
        log.append("task", {"n": 1}, trace_id="t-1", source="test")
        replayed = log.replay()
        assert replayed[0]["payload"] == {"n": 1}
        assert replayed[0]["trace_id"] == "t-1"

    def test_default_capacity_is_10000(self):
        """La capacidad por defecto documentada es 10 000 eventos."""
        log = EventLog()
        for n in range(10_000):
            log.append(f"k{n}")
        with pytest.raises(EventLogFullError, match="max=10000"):
            log.append("extra")

    def test_construction_validates_arguments(self):
        """max_entries <= 0 y overflow desconocido son errores accionables."""
        with pytest.raises(ValueError, match="max_entries"):
            EventLog(max_entries=0)
        with pytest.raises(ValueError, match="overflow invalido"):
            EventLog(overflow="descartar")

    def test_append_defaults_are_empty(self):
        """Sin indicar nada, trace_id/source quedan vacíos y payload {}, no None."""
        log = EventLog()
        envelope = log.append("a")
        assert envelope.trace_id == ""
        assert envelope.source == ""
        assert envelope.payload == {}
        replayed = log.replay()
        assert replayed[0]["trace_id"] == ""
        assert replayed[0]["source"] == ""

    def test_explicit_seq_replays_and_advances(self):
        """seq explícita (replay) fija el envelope y mueve el cursor."""
        log = EventLog()
        replayed = log.append("a", seq=5)
        assert replayed.seq == 5
        assert log.next_seq == 6
        assert log.append("b").seq == 6

    def test_clear_empties_and_restarts_sequence(self):
        """clear() vacía el log y reinicia la secuencia a 1."""
        log = EventLog()
        log.append("a")
        log.clear()
        assert len(log) == 0
        assert log.entries() == ()
        assert log.next_seq == 1
        assert log.append("b").seq == 1

    def test_payload_is_frozen_mapping(self):
        """El payload del envelope del log queda congelado (MappingProxy)."""
        log = EventLog()
        envelope = log.append("a", {"n": 1})
        assert isinstance(envelope.payload, MappingProxyType)
        with pytest.raises(TypeError):
            envelope.payload["n"] = 2  # type: ignore[index]


class TestKernelLoop:
    """Dispatch determinista FIFO y política de errores."""

    def _loop(self, fail_fast: bool = False) -> KernelLoop:
        return KernelLoop(BoundedMailbox(capacity=8), EventLog(), fail_fast=fail_fast)

    def test_dispatch_order_is_fifo(self):
        """Los handlers se ejecutan en el orden de envío."""
        loop = self._loop()
        order: list[int] = []
        loop.register("task", lambda payload, _env: order.append(payload["n"]))
        for n in (1, 2, 3):
            loop.submit("task", {"n": n})
        assert loop.run() == 3
        assert order == [1, 2, 3]

    def test_trace_id_and_seq_propagate(self):
        """El handler recibe el envelope con trace_id y seq."""
        loop = self._loop()
        seen: list[tuple[int, str]] = []
        loop.register("task", lambda _p, env: seen.append((env.seq, env.trace_id)))
        loop.submit("task", {}, trace_id="trace-9")
        loop.run()
        assert seen == [(1, "trace-9")]

    def test_handler_error_does_not_stop_by_default(self):
        """Sin fail_fast, un handler que falla se registra y el loop sigue."""
        loop = self._loop()
        loop.register("boom", lambda _p, _e: (_ for _ in ()).throw(RuntimeError("x")))
        loop.register("ok", lambda _p, _e: None)
        loop.submit("boom")
        loop.submit("ok")
        assert loop.run() == 2
        assert loop.stats.errors == 1
        assert any(entry.kind == "kernel.error" for entry in loop._log.entries())

    def test_fail_fast_propagates_handler_error(self):
        """Con fail_fast, el error del handler aborta el dispatch."""
        loop = self._loop(fail_fast=True)
        loop.register("boom", lambda _p, _e: (_ for _ in ()).throw(RuntimeError("x")))
        loop.submit("boom")
        with pytest.raises(RuntimeError):
            loop.run()
        assert loop.stats.errors == 1

    def test_unregistered_kind_is_counted(self):
        """Un kind sin handler se contabiliza y se registra en el log."""
        loop = self._loop()
        loop.submit("nadie")
        assert loop.run() == 1
        assert loop.stats.unregistered == 1
        assert any(entry.kind == "kernel.unregistered" for entry in loop._log.entries())

    def test_fail_fast_unregistered_raises(self):
        """Con fail_fast, un kind sin handler es error duro."""
        loop = self._loop(fail_fast=True)
        loop.submit("nadie")
        with pytest.raises(UnregisteredKindError):
            loop.run()

    def test_submit_backpressure(self):
        """submit propaga MailboxFullError cuando el buzón está lleno."""
        loop = KernelLoop(BoundedMailbox(capacity=1), EventLog())
        loop.submit("task")
        with pytest.raises(MailboxFullError):
            loop.submit("task")

    def test_run_max_messages(self):
        """run(max_messages) procesa solo el lote pedido."""
        loop = self._loop()
        loop.register("task", lambda _p, _e: None)
        for _ in range(5):
            loop.submit("task")
        assert loop.run(max_messages=2) == 2
        assert len(loop._mailbox) == 3
        assert loop.stats.dispatched == 2

    def test_default_fail_fast_is_off(self):
        """Sin indicarlo, un handler que falla no aborta (fail_fast=False)."""
        loop = KernelLoop(BoundedMailbox(capacity=8), EventLog())
        loop.register("boom", _raiser)
        loop.submit("boom")
        assert loop.run() == 1
        assert loop.stats.errors == 1

    def test_requires_mailbox_and_event_log(self):
        """Los dos dependientes son obligatorios (mensaje accionable)."""
        with pytest.raises(ValueError, match="obligatorios"):
            KernelLoop(None, EventLog())  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="obligatorios"):
            KernelLoop(BoundedMailbox(), None)  # type: ignore[arg-type]

    def test_register_validates_kind_and_handler(self):
        """register rechaza kind vacío/no-str y handler no callable."""
        loop = self._loop()
        with pytest.raises(ValueError, match="kind vacio"):
            loop.register("", lambda _p, _e: None)
        with pytest.raises(ValueError, match="kind vacio"):
            loop.register("   ", lambda _p, _e: None)
        with pytest.raises(TypeError, match="handler no callable"):
            loop.register("task", 42)  # type: ignore[arg-type]
        loop.register("task", lambda _p, _e: None)
        assert "task" in loop._handlers

    def test_submit_defaults_and_mirrors_into_log(self):
        """submit usa defaults vacíos y replica el envelope en el log."""
        loop = self._loop()
        envelope = loop.submit("task", {"n": 1})
        assert (envelope.trace_id, envelope.source) == ("", "")
        assert envelope.seq == 1
        stored = loop._log.entries()[-1]
        assert (stored.seq, stored.kind) == (1, "task")
        assert (stored.trace_id, stored.source) == ("", "")
        assert dict(stored.payload) == {"n": 1}

    def test_submit_propagates_trace_id_and_source(self):
        """trace_id/source llegan al envelope y a su copia del log."""
        loop = self._loop()
        envelope = loop.submit("task", {}, trace_id="t-7", source="agente")
        assert (envelope.trace_id, envelope.source) == ("t-7", "agente")
        stored = loop._log.entries()[-1]
        assert (stored.trace_id, stored.source) == ("t-7", "agente")

    def test_submit_backpressure_keeps_log_untouched(self):
        """Si el buzón está lleno, el log NO registra el rechazo."""
        loop = KernelLoop(BoundedMailbox(capacity=1), EventLog())
        loop.submit("task")
        with pytest.raises(MailboxFullError):
            loop.submit("task")
        assert len(loop._log) == 1

    def test_dispatch_counts_by_kind(self):
        """by_kind acumula (no sustituye) y dispatched cuenta cada ejecución."""
        loop = self._loop()
        loop.register("a", lambda _p, _e: None)
        loop.register("b", lambda _p, _e: None)
        for kind in ("a", "b", "a", "b"):
            loop.submit(kind)
        assert loop.run() == 4
        assert loop.stats.by_kind == {"a": 2, "b": 2}
        assert loop.stats.dispatched == 4

    def test_unregistered_counter_accumulates_and_logs_context(self):
        """Cada kind sin handler suma y deja kind/seq/trace/source en el log."""
        loop = self._loop()
        loop.submit("nadie", {}, trace_id="t-1")
        loop.submit("otro", {}, trace_id="t-2")
        assert loop.run() == 2
        assert loop.stats.unregistered == 2
        entries = [e for e in loop._log.entries() if e.kind == "kernel.unregistered"]
        assert [e.payload["kind"] for e in entries] == ["nadie", "otro"]
        assert [e.payload["seq"] for e in entries] == [1, 2]
        assert [e.trace_id for e in entries] == ["t-1", "t-2"]
        assert all(e.source == "kernel" for e in entries)

    def test_unregistered_fail_fast_message_is_actionable(self):
        """Con fail_fast el error identifica kind y seq."""
        loop = self._loop(fail_fast=True)
        loop.submit("nadie")
        with pytest.raises(
            UnregisteredKindError, match=r"kind_sin_handler.*kind='nadie'"
        ):
            loop.run()

    def test_handler_error_counter_accumulates_and_logs_error(self):
        """Cada fallo suma errors y deja el error formateado en el log."""
        loop = self._loop()
        loop.register("boom", _raiser)
        loop.submit("boom", {}, trace_id="t-9")
        loop.submit("boom", {}, trace_id="t-10")
        assert loop.run() == 2
        assert loop.stats.errors == 2
        entries = [e for e in loop._log.entries() if e.kind == "kernel.error"]
        assert len(entries) == 2
        assert [e.payload["error"] for e in entries] == ["RuntimeError: boom"] * 2
        assert [e.payload["kind"] for e in entries] == ["boom", "boom"]
        assert [e.trace_id for e in entries] == ["t-9", "t-10"]
        assert all(e.source == "kernel" for e in entries)

    def test_fail_fast_re_raise_keeps_original_message(self):
        """Con fail_fast se relanza la excepción original con su mensaje."""
        loop = self._loop(fail_fast=True)
        loop.register("boom", _raiser)
        loop.submit("boom")
        with pytest.raises(RuntimeError, match="boom"):
            loop.run()

    def test_stats_snapshot_is_a_copy(self):
        """stats() devuelve un snapshot: mutarlo no toca el estado real."""
        loop = self._loop()
        snapshot = loop.stats
        snapshot.dispatched = 99
        snapshot.by_kind["k"] = 99
        assert loop.stats.dispatched == 0
        assert loop.stats.by_kind == {}
