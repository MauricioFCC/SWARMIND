"""Tests para SharedSemanticCache, EventBus, SpeculativeDecoder, KVCacheSharing, A2AProtocol."""

from __future__ import annotations

import time

from harness.memory_rag.kv_cache_sharing import KVCacheSharing
from harness.memory_rag.shared_cache import SharedSemanticCache
from harness.orchestrator.a2a_protocol import (
    A2AProtocol,
    AgentCapability,
    AgentRole,
    MessageType,
)
from harness.orchestrator.event_bus import Event, EventBus, EventPriority
from harness.orchestrator.speculative_decoder import (
    SpeculativeDecoder,
    SpeculativeResult,
)

# ============================================================================
# SharedSemanticCache Tests
# ============================================================================

class TestSharedSemanticCache:
    def setup_method(self) -> None:
        self.cache = SharedSemanticCache(capacity=10, ttl=3600, threshold=0.5)

    def test_set_and_get(self) -> None:
        self.cache.set("consulta", "resultado", "gpt-4", "agent_1")
        result = self.cache.get("consulta", "agent_2")
        assert result == "resultado"

    def test_miss_on_different(self) -> None:
        self.cache = SharedSemanticCache(capacity=10, ttl=3600, threshold=0.95)
        self.cache.set("hola mundo", "resultado_a", "gpt-4", "a")
        result = self.cache.get("xyz algo completamente diferente abc 123", "b")
        assert result is None

    def test_stats(self) -> None:
        self.cache = SharedSemanticCache(capacity=10, ttl=3600, threshold=0.95)
        self.cache.set("test único 123", "res", "gpt-4", "a")
        self.cache.get("test único 123", "b")
        self.cache.get("xyz algo completamente diferente y único abc 999", "b")
        stats = self.cache.get_stats()
        assert stats.total_hits >= 1
        assert stats.total_misses >= 1
        assert stats.hit_rate > 0

    def test_clear(self) -> None:
        self.cache.set("a", "1", "gpt-4", "a")
        self.cache.set("b", "2", "gpt-4", "b")
        assert self.cache.size == 2
        self.cache.clear()
        assert self.cache.size == 0

    def test_eviction(self) -> None:
        small_cache = SharedSemanticCache(capacity=3, threshold=0.0)
        for i in range(5):
            small_cache.set(f"key{i}", f"val{i}", "gpt-4", "a")
        assert small_cache.size <= 3


# ============================================================================
# EventBus Tests
# ============================================================================

class TestEventBus:
    def setup_method(self) -> None:
        self.bus = EventBus()

    def test_subscribe_and_publish(self) -> None:
        received: list[Event] = []
        self.bus.subscribe("test:channel", lambda e: received.append(e))
        event = Event(
            event_id="e1", channel="test:channel",
            data={"msg": "hello"}, source="agent_1",
            priority=EventPriority.NORMAL, timestamp=time.time(),
        )
        self.bus.publish(event)
        assert len(received) == 1
        assert received[0].data["msg"] == "hello"

    def test_wildcard_subscribe(self) -> None:
        received: list[Event] = []
        self.bus.subscribe("task:*", lambda e: received.append(e))
        e1 = Event("e1", "task:complete", {"id": 1}, "a", EventPriority.NORMAL, time.time())
        e2 = Event("e2", "task:failed", {"id": 2}, "a", EventPriority.NORMAL, time.time())
        e3 = Event("e3", "other:event", {"id": 3}, "a", EventPriority.NORMAL, time.time())
        self.bus.publish(e1)
        self.bus.publish(e2)
        self.bus.publish(e3)
        assert len(received) == 2

    def test_unsubscribe(self) -> None:
        received: list[Event] = []
        sub_id = self.bus.subscribe("test", lambda e: received.append(e))
        self.bus.publish(Event("e1", "test", {}, "a", EventPriority.NORMAL, time.time()))
        assert len(received) == 1
        self.bus.unsubscribe(sub_id)
        self.bus.publish(Event("e2", "test", {}, "a", EventPriority.NORMAL, time.time()))
        assert len(received) == 1

    def test_get_stats(self) -> None:
        self.bus.subscribe("chan", lambda e: None)
        stats = self.bus.get_stats()
        assert stats["total_subscriptions"] >= 1

    def test_clear(self) -> None:
        self.bus.subscribe("a", lambda e: None)
        self.bus.subscribe("b", lambda e: None)
        assert self.bus.clear() == 2


# ============================================================================
# SpeculativeDecoder Tests
# ============================================================================

class TestSpeculativeDecoder:
    def test_generate(self) -> None:
        def draft_fn(prompt: str, n: int) -> list[str]:
            return [f" token{i}" for i in range(n)]

        def verify_fn(prompt: str, candidates: list[str]) -> list[bool]:
            return [True] * len(candidates)

        decoder = SpeculativeDecoder(draft_fn, verify_fn)
        result = decoder.generate("hello")
        assert isinstance(result, SpeculativeResult)
        assert result.tokens_drafted > 0
        assert result.text != ""

    def test_acceptance_rate(self) -> None:
        def draft_fn(prompt: str, n: int) -> list[str]:
            return [f" tok{i}" for i in range(n)]

        def verify_fn(prompt: str, candidates: list[str]) -> list[bool]:
            return [True] * len(candidates)

        decoder = SpeculativeDecoder(draft_fn, verify_fn)
        result = decoder.generate("test")
        assert result.acceptance_rate == 1.0

    def test_get_stats(self) -> None:
        def draft_fn(p: str, n: int) -> list[str]:
            return [" tok"] * n
        def verify_fn(p: str, c: list[str]) -> list[bool]:
            return [True] * len(c)

        decoder = SpeculativeDecoder(draft_fn, verify_fn)
        decoder.generate("hello")
        stats = decoder.get_stats()
        assert stats["total_calls"] >= 1


# ============================================================================
# KVCacheSharing Tests
# ============================================================================

class TestKVCacheSharing:
    def setup_method(self) -> None:
        self.cache = KVCacheSharing(capacity=10)

    def test_store_and_get(self) -> None:
        self.cache.store("prompt de prueba", "gpt-4", "agent_a", 512)
        entry = self.cache.get("prompt de prueba")
        assert entry is not None
        assert entry.model == "gpt-4"

    def test_miss(self) -> None:
        entry = self.cache.get("no existe", min_prefix=5)
        assert entry is None

    def test_stats(self) -> None:
        self.cache.store("a", "gpt-4", "a1", 100)
        self.cache.get("a")
        self.cache.get("no_existe")
        stats = self.cache.get_stats()
        assert stats.total_hits >= 1
        assert stats.total_misses >= 1

    def test_clear(self) -> None:
        self.cache.store("a", "gpt-4", "a", 100)
        assert self.cache.size == 1
        self.cache.clear()
        assert self.cache.size == 0


# ============================================================================
# A2AProtocol Tests
# ============================================================================

class TestA2AProtocol:
    def test_register_and_discover(self) -> None:
        agent = A2AProtocol("agent_1", AgentRole.WORKER, [
            AgentCapability("code", "Code generation"),
        ])
        agent.register()
        discovered = agent.discover("code")
        assert len(discovered) >= 1
        assert discovered[0].agent_id == "agent_1"

    def test_send_message(self) -> None:
        agent_a = A2AProtocol("agent_a", AgentRole.COORDINATOR, [])
        agent_b = A2AProtocol("agent_b", AgentRole.WORKER, [])
        agent_a.register()
        agent_b.register()

        # Registrar manualmente (simulando discovery)
        agent_a._agents["agent_b"] = agent_b._agents["agent_b"]

        msg = agent_a.send_message("agent_b", MessageType.TASK_REQUEST, {"task": "test"})
        assert msg.msg_type == MessageType.TASK_REQUEST
        assert msg.payload["task"] == "test"

    def test_discover_by_capability(self) -> None:
        agent = A2AProtocol("agent_c", AgentRole.SPECIALIST, [
            AgentCapability("security", "Security audit"),
            AgentCapability("code", "Code review"),
        ])
        agent.register()
        security_agents = agent.discover("security")
        assert len(security_agents) >= 1

    def test_get_stats(self) -> None:
        agent = A2AProtocol("agent_s", AgentRole.WORKER, [AgentCapability("test", "Test")])
        agent.register()
        stats = agent.get_stats()
        assert stats["agent_id"] == "agent_s"
        assert stats["known_agents"] >= 1
