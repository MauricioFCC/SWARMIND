"""Tests para AgentBus."""
from __future__ import annotations
import pytest


class TestAgentBus:
    def test_post_message(self, agent_bus):
        msg_id = agent_bus.post_message("#test", "@a", "@b", "hello", "notification")
        assert msg_id is not None
        assert isinstance(msg_id, str)
        assert len(msg_id) > 0

    def test_invalid_channel(self, agent_bus):
        with pytest.raises(Exception):
            agent_bus.post_message("bad", "@a", "@b", "x", "notification")

    def test_poll_channel(self, agent_bus):
        agent_bus.post_message("#ch", "@a", "@b", "msg1", "notification")
        agent_bus.post_message("#ch", "@a", "@b", "msg2", "notification")
        msgs = agent_bus.poll_channel("#ch", "@b")
        assert len(msgs) >= 1

    def test_count_iterations(self, agent_bus):
        tid = "task-001"
        agent_bus.post_message("#t", "@a", "@b", "e1", "error", task_id=tid)
        agent_bus.post_message("#t", "@a", "@b", "e2", "error", task_id=tid)
        assert agent_bus.count_iterations(tid) >= 2

    def test_circuit_breaker(self, agent_bus):
        tid = "cb-001"
        for i in range(5):
            agent_bus.post_message("#t", "@a", "@b", f"e{i}", "error", task_id=tid)
        assert agent_bus.check_circuit_breaker(tid, max_iterations=5) is True
        assert agent_bus.check_circuit_breaker(tid, max_iterations=10) is False

    def test_message_by_id(self, agent_bus):
        mid = agent_bus.post_message("#t", "@a", "@b", "test", "notification")
        msg = agent_bus.get_message_by_id(mid)
        assert msg is not None
        assert msg["message"] == "test"
