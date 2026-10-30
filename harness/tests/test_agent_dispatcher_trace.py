"""Tests de correlación req/resp del AgentDispatcher (AC-KN5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from harness.orchestrator.agent_dispatcher import AgentDispatcher


@pytest.fixture
def dispatcher() -> AgentDispatcher:
    """Dispatcher con store mockeado (sin LanceDB real)."""
    store = MagicMock()
    store.search.return_value = []
    return AgentDispatcher(vector_store=store)


class TestTraceCorrelation:
    """AC-KN5: trace_id correlacionado y evento agent.dispatch."""

    def test_generated_trace_id_is_returned(self, dispatcher) -> None:
        """Sin trace_id explícito se genera uno y viaja en el resultado."""
        with patch.object(dispatcher, "find_skill_for_task", return_value=None):
            result = dispatcher.dispatch("builder", "tarea sin skill")
        assert len(result["trace_id"]) == 32

    def test_explicit_trace_id_is_propagated(self, dispatcher) -> None:
        """El trace_id explícito se devuelve sin cambios."""
        with patch.object(dispatcher, "find_skill_for_task", return_value=None):
            result = dispatcher.dispatch("builder", "tarea", trace_id="trace-42")
        assert result["trace_id"] == "trace-42"

    def test_bus_receives_agent_dispatch_event(self) -> None:
        """Con bus, se publica agent.dispatch con el trace correlacionado."""
        store = MagicMock()
        store.search.return_value = []

        class _Bus:
            def __init__(self) -> None:
                self.events: list[tuple[str, dict, str, str]] = []

            def publish(
                self, kind, payload=None, *, trace_id="", source="", drain=True
            ):
                self.events.append((kind, dict(payload or {}), trace_id, source))

        bus = _Bus()
        dispatcher = AgentDispatcher(vector_store=store, bus=bus)
        with patch.object(dispatcher, "find_skill_for_task", return_value=None):
            dispatcher.dispatch("qa", "revisar", trace_id="t-1")
        assert bus.events[0][0] == "agent.dispatch"
        assert bus.events[0][2] == "t-1"
        assert bus.events[0][1]["agent"] == "qa"
