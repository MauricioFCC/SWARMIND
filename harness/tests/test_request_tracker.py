"""Tests del RequestTracker (correlación req/resp + timeout tipado, AC-KN5)."""

from __future__ import annotations

import pytest

from harness.orchestrator.agent_bus import KernelBus
from harness.orchestrator.request_tracker import RequestTimeoutError, RequestTracker


def _echo_bus() -> KernelBus:
    """Bus con un handler ``echo`` que responde con el mismo ``trace_id``."""
    bus = KernelBus()

    def _echo(payload, envelope):
        bus.publish(
            "echo.reply",
            {"echo": payload["x"]},
            trace_id=envelope.trace_id,
            source="echo",
        )

    bus.subscribe("echo", _echo)
    return bus


class FakeClock:
    """Reloj monótono falso: devuelve los valores en orden."""

    def __init__(self, *values: float) -> None:
        self._values = list(values)

    def __call__(self) -> float:
        return self._values.pop(0)


class TestRequestTracker:
    """Contrato de correlación y errores tipados."""

    def test_returns_correlated_reply(self):
        """La respuesta del mismo trace se devuelve como payload."""
        tracker = RequestTracker(_echo_bus())
        assert tracker.request(
            "echo", {"x": 1}, reply_kind="echo.reply", timeout_s=1.0
        ) == {"echo": 1}

    def test_custom_trace_id_is_propagated(self):
        """El trace_id explícito viaja en la petición y la respuesta."""
        bus = KernelBus()
        seen: list[str] = []

        def _echo(payload, envelope):
            seen.append(envelope.trace_id)
            bus.publish("echo.reply", {"ok": True}, trace_id=envelope.trace_id)

        bus.subscribe("echo", _echo)
        tracker = RequestTracker(bus)
        tracker.request(
            "echo", {}, reply_kind="echo.reply", timeout_s=1.0, trace_id="trace-x"
        )
        assert seen == ["trace-x"]

    def test_timeout_when_no_reply(self):
        """Sin respuesta correlacionada se lanza RequestTimeoutError."""
        bus = KernelBus()  # nadie responde
        tracker = RequestTracker(bus)
        with pytest.raises(RequestTimeoutError) as excinfo:
            tracker.request("echo", {}, reply_kind="echo.reply", timeout_s=0.5)
        assert "sin_respuesta" in str(excinfo.value)
        assert excinfo.value.trace_id

    def test_timeout_when_deadline_exceeded(self):
        """Una respuesta que llega fuera de presupuesto también es timeout."""
        tracker = RequestTracker(_echo_bus(), clock=FakeClock(0.0, 2.0))
        with pytest.raises(RequestTimeoutError) as excinfo:
            tracker.request("echo", {"x": 2}, reply_kind="echo.reply", timeout_s=1.0)
        assert "timeout" in str(excinfo.value)

    def test_reply_with_other_trace_is_ignored(self):
        """Una respuesta con otro trace_id no satisface la petición."""
        bus = KernelBus()
        bus.subscribe(
            "echo",
            lambda _payload, env: bus.publish(
                "echo.reply", {"ok": True}, trace_id="otro"
            ),
        )
        tracker = RequestTracker(bus)
        with pytest.raises(RequestTimeoutError):
            tracker.request(
                "echo", {}, reply_kind="echo.reply", timeout_s=1.0, trace_id="mio"
            )

    def test_rejects_non_positive_timeout(self):
        """timeout_s <= 0 es error de programación (fail-fast)."""
        tracker = RequestTracker(_echo_bus())
        with pytest.raises(ValueError):
            tracker.request("echo", {}, reply_kind="echo.reply", timeout_s=0)

    def test_rejects_invalid_bus(self):
        """Un objeto sin subscribe/publish no cumple el puerto."""
        with pytest.raises(ValueError):
            RequestTracker(object())  # type: ignore[arg-type]

    def test_two_requests_do_not_mix_replies(self):
        """El mapa de respuestas se consume por trace (sin fugas cruzadas)."""
        tracker = RequestTracker(_echo_bus())
        first = tracker.request(
            "echo", {"x": 1}, reply_kind="echo.reply", timeout_s=1.0, trace_id="a"
        )
        second = tracker.request(
            "echo", {"x": 2}, reply_kind="echo.reply", timeout_s=1.0, trace_id="b"
        )
        assert (first["echo"], second["echo"]) == (1, 2)
