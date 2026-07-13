"""
Tests extendidos para SemanticCache — cubre paths no cubiertos por test_cache.py.

Cubre:
  - CacheEntry.is_expired() con TTL
  - set() method with various params
  - get_stats() comprehensive
  - clear_expired()
  - _normalize_similarity() for both LanceDB and in-memory
  - clear()
  - get() with custom thresholds
  - _is_expired() static method
  - CacheEntry.to_dict()
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from harness.memory_rag.semantic_cache import (
    COLLECTION_SEMANTIC_CACHE,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_TTL_SECONDS,
    CacheEntry,
    SemanticCache,
)
from harness.common import fallback_embedding


# ---------------------------------------------------------------------------
# CacheEntry tests
# ---------------------------------------------------------------------------


class TestCacheEntry:
    def test_create_defaults(self):
        entry = CacheEntry(
            prompt_hash="abc123",
            prompt_text="hello",
            response="world",
            agent_role="builder",
        )
        assert entry.prompt_hash == "abc123"
        assert entry.prompt_text == "hello"
        assert entry.response == "world"
        assert entry.agent_role == "builder"
        assert entry.hit_count == 1
        assert entry.ttl_seconds == DEFAULT_TTL_SECONDS
        assert entry.metadata == {}

    def test_is_expired_fresh(self):
        now = datetime.now(timezone.utc).isoformat()
        entry = CacheEntry(
            prompt_hash="abc",
            prompt_text="test",
            response="resp",
            agent_role="*",
            created_at=now,
            ttl_seconds=3600,
        )
        assert not entry.is_expired()

    def test_is_expired_old(self):
        old = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
        entry = CacheEntry(
            prompt_hash="abc",
            prompt_text="test",
            response="resp",
            agent_role="*",
            created_at=old,
            ttl_seconds=1,
        )
        assert entry.is_expired()

    def test_is_expired_no_created_at(self):
        entry = CacheEntry(
            prompt_hash="abc",
            prompt_text="test",
            response="resp",
            agent_role="*",
            created_at="",
        )
        assert entry.is_expired()

    def test_is_expired_invalid_date(self):
        entry = CacheEntry(
            prompt_hash="abc",
            prompt_text="test",
            response="resp",
            agent_role="*",
            created_at="not-a-date",
        )
        assert entry.is_expired()

    def test_to_dict(self):
        entry = CacheEntry(
            prompt_hash="abc123",
            prompt_text="hello world",
            response="goodbye world",
            agent_role="builder",
            hit_count=3,
            created_at="2024-01-01T00:00:00",
            last_accessed="2024-01-02T00:00:00",
            ttl_seconds=7200,
            metadata={"key": "val"},
        )
        d = entry.to_dict()
        assert d["prompt_hash"] == "abc123"
        assert d["prompt_text"] == "hello world"
        assert d["response"] == "goodbye world"
        assert d["agent_role"] == "builder"
        assert d["hit_count"] == 3
        assert d["created_at"] == "2024-01-01T00:00:00"
        assert d["last_accessed"] == "2024-01-02T00:00:00"
        assert d["ttl_seconds"] == 7200

    def test_to_dict_truncates_prompt_text(self):
        long_text = "x" * 1000
        entry = CacheEntry(
            prompt_hash="abc",
            prompt_text=long_text,
            response="resp",
            agent_role="*",
        )
        d = entry.to_dict()
        assert len(d["prompt_text"]) == 500


# ---------------------------------------------------------------------------
# SemanticCache extended tests
# ---------------------------------------------------------------------------


class TestSemanticCacheSet:
    def test_set_returns_true(self, semantic_cache):
        result = semantic_cache.set("prompt", "response", agent_role="test")
        assert result is True

    def test_set_stores_and_can_retrieve(self, semantic_cache):
        semantic_cache.set("hello prompt", "hello response", agent_role="builder")
        result = semantic_cache.get("hello prompt", agent_role="builder")
        assert result == "hello response"

    def test_set_with_custom_ttl(self, semantic_cache):
        semantic_cache.set("p", "r", agent_role="*", ttl_seconds=30)
        # Verify stats reflect
        stats = semantic_cache.get_stats()
        assert stats["default_ttl_seconds"] == DEFAULT_TTL_SECONDS
        assert stats["sets"] >= 1

    def test_set_with_metadata(self, semantic_cache):
        semantic_cache.set("p", "r", agent_role="test", metadata={"version": 1})
        result = semantic_cache.get("p", agent_role="test")
        assert result == "r"

    def test_set_multiple_entries(self, semantic_cache):
        semantic_cache.set("q1", "a1", agent_role="builder")
        semantic_cache.set("q2", "a2", agent_role="scientist")
        assert semantic_cache.get("q1", agent_role="builder") == "a1"
        assert semantic_cache.get("q2", agent_role="scientist") == "a2"


class TestSemanticCacheGetStats:
    def test_stats_structure(self, semantic_cache):
        stats = semantic_cache.get_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "sets" in stats
        assert "expired" in stats
        assert "total_requests" in stats
        assert "hit_rate" in stats
        assert "collection" in stats
        assert stats["collection"] == COLLECTION_SEMANTIC_CACHE
        assert stats["threshold"] == DEFAULT_SIMILARITY_THRESHOLD
        assert stats["default_ttl_seconds"] == DEFAULT_TTL_SECONDS

    def test_stats_hit_rate_after_miss(self, semantic_cache):
        semantic_cache.get("unknown", agent_role="test")
        stats = semantic_cache.get_stats()
        assert stats["total_requests"] == 1
        assert stats["misses"] == 1
        assert stats["hits"] == 0
        assert stats["hit_rate"] == 0.0

    def test_stats_hit_rate_after_hit(self, semantic_cache):
        semantic_cache.set("prompt", "response", agent_role="test")
        semantic_cache.get("prompt", agent_role="test")
        stats = semantic_cache.get_stats()
        assert stats["total_requests"] == 1
        assert stats["hits"] == 1
        assert stats["hit_rate"] == 100.0

    def test_stats_increments_sets(self, semantic_cache):
        semantic_cache.set("p1", "r1", agent_role="*")
        semantic_cache.set("p2", "r2", agent_role="*")
        stats = semantic_cache.get_stats()
        assert stats["sets"] == 2


class TestSemanticCacheClearExpired:
    def test_clear_expired_returns_zero(self, semantic_cache):
        """clear_expired is largely a no-op for LanceDB backend."""
        result = semantic_cache.clear_expired()
        assert result == 0


class TestSemanticCacheClear:
    def test_clear_returns_int(self, semantic_cache):
        result = semantic_cache.clear()
        assert isinstance(result, int)


class TestNormalizeSimilarity:
    def test_lancedb_mode_converts_l2(self):
        """When LanceDB is available, simulate L2→similarity conversion."""
        cache = SemanticCache()
        # Simulate LanceDB mode
        with patch.object(cache._store, '_lancedb_available', True):
            # L2=0 → sim=1.0
            assert cache._normalize_similarity(0.0) == 1.0
            # L2=0.1 → sim≈0.909
            sim = cache._normalize_similarity(0.1)
            assert abs(sim - 0.90909) < 0.001
            # L2=1.0 → sim=0.5
            assert cache._normalize_similarity(1.0) == 0.5

    def test_inmemory_mode_clamps_cosine(self):
        """In-memory mode uses cosine similarity directly, clamped to [0,1]."""
        cache = SemanticCache()
        # Simulate in-memory mode
        with patch.object(cache._store, '_lancedb_available', False):
            assert cache._normalize_similarity(1.0) == 1.0
            assert cache._normalize_similarity(0.5) == 0.5
            assert cache._normalize_similarity(0.0) == 0.0
            # Negative values clamped to 0
            assert cache._normalize_similarity(-0.5) == 0.0
            # Values >1 clamped to 1
            assert cache._normalize_similarity(1.5) == 1.0


class TestIsExpired:
    def test_fresh_not_expired(self):
        now = datetime.now(timezone.utc).isoformat()
        assert not SemanticCache._is_expired(now, 3600)

    def test_expired_by_ttl(self):
        old = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
        assert SemanticCache._is_expired(old, 1)

    def test_empty_created_at(self):
        assert SemanticCache._is_expired("", 3600)

    def test_invalid_date(self):
        assert SemanticCache._is_expired("not-a-date", 3600)


class TestHashPrompt:
    def test_hash_is_deterministic(self):
        h1 = SemanticCache._hash_prompt("hello world")
        h2 = SemanticCache._hash_prompt("hello world")
        assert h1 == h2

    def test_hash_differs_for_different_text(self):
        h1 = SemanticCache._hash_prompt("hello")
        h2 = SemanticCache._hash_prompt("world")
        assert h1 != h2

    def test_hash_is_sha256_hex(self):
        h = SemanticCache._hash_prompt("test")
        assert len(h) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in h)


class TestDefaultEmbedding:
    def test_delegates_to_fallback(self):
        vec = SemanticCache._default_embedding("hello")
        expected = fallback_embedding("hello")
        assert np.allclose(vec, expected)

    def test_returns_normalized_vector(self):
        vec = SemanticCache._default_embedding("test")
        assert abs(np.linalg.norm(vec) - 1.0) < 1e-6


class TestSemanticCacheGetThreshold:
    def test_custom_threshold_on_get(self, semantic_cache):
        """get() accepts a per-request threshold override."""
        semantic_cache.set("prompt", "response", agent_role="test")
        # With a very high threshold, it might still match exact hash
        result = semantic_cache.get("prompt", agent_role="test", threshold=0.99)
        assert result == "response"

    def test_agent_role_filtering(self, semantic_cache):
        """get() with agent_role='*' should match any."""
        semantic_cache.set("prompt", "response", agent_role="builder")
        result = semantic_cache.get("prompt", agent_role="*")
        assert result == "response"

    def test_different_agent_role_miss(self, semantic_cache):
        """get() with a different agent_role that doesn't match should miss."""
        semantic_cache.set("prompt", "response", agent_role="builder")
        result = semantic_cache.get("prompt", agent_role="scientist")
        # _search_exact checks agent_role: "builder" not in ("scientist", "*")
        assert result is None


class TestSemanticCacheEdgeCases:
    def test_empty_prompt_returns_none(self, semantic_cache):
        result = semantic_cache.get("", agent_role="test")
        assert result is None

    def test_empty_response_set(self, semantic_cache):
        result = semantic_cache.set("prompt", "", agent_role="test")
        assert result is True

    def test_get_on_empty_cache(self, semantic_cache):
        result = semantic_cache.get("anything", agent_role="*")
        assert result is None

    def test_very_long_prompt(self, semantic_cache):
        long_prompt = "test " * 1000
        semantic_cache.set(long_prompt, "response", agent_role="test")
        result = semantic_cache.get(long_prompt, agent_role="test")
        assert result == "response"


class TestSemanticCacheInit:
    def test_init_with_custom_threshold(self):
        cache = SemanticCache(threshold=0.5)
        assert cache._threshold == 0.5

    def test_init_with_custom_ttl(self):
        cache = SemanticCache(default_ttl=60)
        assert cache._default_ttl == 60

    def test_init_with_custom_embedding_fn(self):
        custom_fn = lambda x: np.ones(384, dtype=np.float32)
        cache = SemanticCache(embedding_fn=custom_fn)
        result = cache._embedding_fn("test")
        assert np.all(result == 1.0)
