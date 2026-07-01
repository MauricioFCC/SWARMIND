"""Tests para SemanticCache."""
from __future__ import annotations


class TestCache:
    def test_set_and_get(self, semantic_cache):
        semantic_cache.set("prompt", "response", agent_role="test")
        result = semantic_cache.get("prompt", agent_role="test")
        assert result == "response"

    def test_cache_miss(self, semantic_cache):
        result = semantic_cache.get("unknown", agent_role="test")
        assert result is None

    def test_stats(self, semantic_cache):
        stats = semantic_cache.get_stats()
        assert "hits" in stats
        assert "misses" in stats
