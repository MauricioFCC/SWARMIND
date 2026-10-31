"""Tests del kernel event-driven de SWARMIND (mensajes, mailbox, event log)."""

from __future__ import annotations

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
