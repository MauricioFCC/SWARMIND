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

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np

from harness.memory_rag.semantic_cache import (
    COLLECTION_SEMANTIC_CACHE,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_TTL_SECONDS,
    CacheEntry,
    SemanticCache,
    ShapedCache,
)

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
    def test_clear_expired_returns_int(self, semantic_cache):
        """clear_expired returns count of removed expired entries (>=0)."""
        result = semantic_cache.clear_expired()
        assert isinstance(result, int)
        assert result >= 0


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


# ---------------------------------------------------------------------------
# ShapedCache — Cache-Shape Discipline tests
# ---------------------------------------------------------------------------


class TestShapedCache:
    """Tests para ShapedCache — Cache-Shape Discipline (-38% tokens)."""

    def test_shaped_cache_init(self):
        """Constructor con valores por defecto."""
        mock_cache = MagicMock()
        shaped = ShapedCache(mock_cache)

        assert shaped._cache is mock_cache
        assert shaped._max_tokens == 10000
        assert shaped._ttl_sec == 3600.0
        assert shaped._min_relevance == 0.1
        assert len(shaped._lru) == 0
        assert shaped._hit_count == 0
        assert shaped._miss_count == 0
        assert shaped.hit_rate == 0.0

    def test_shaped_cache_get_miss(self):
        """Cache miss retorna None y actualiza contadores."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        shaped = ShapedCache(mock_cache)

        result = shaped.get_shaped("inexistent prompt")

        assert result is None
        assert shaped._miss_count == 1
        assert shaped._hit_count == 0
        assert shaped.hit_rate == 0.0

    def test_shaped_cache_set_and_get(self):
        """Set + Get exitoso retorna la respuesta cacheada."""
        mock_cache = MagicMock()
        mock_cache.set.return_value = True
        mock_cache.get.return_value = {
            "response": "cached answer",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        shaped = ShapedCache(mock_cache)

        # Set
        set_result = shaped.set_shaped("test prompt", "cached answer", token_cost=50)
        assert set_result is True

        # Get
        get_result = shaped.get_shaped("test prompt")
        assert get_result is not None
        assert get_result["response"] == "cached answer"
        assert shaped._hit_count == 1
        assert shaped._miss_count == 0

    def test_shaped_cache_hit_rate(self):
        """Hit rate tracking refleja proporcion hits/misses tras varias consultas."""
        mock_cache = MagicMock()
        shaped = ShapedCache(mock_cache)

        # Miss 1
        mock_cache.get.return_value = None
        shaped.get_shaped("prompt_a")
        assert shaped.hit_rate == 0.0

        # Hit 1
        mock_cache.get.return_value = {
            "response": "resp",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        shaped.get_shaped("prompt_b")
        assert shaped.hit_rate == 0.5

        # Hit 2
        shaped.get_shaped("prompt_c")
        assert shaped.hit_rate == 2 / 3

        assert shaped._hit_count == 2
        assert shaped._miss_count == 1

    def test_shaped_cache_ttl_expiry(self):
        """Entrada expirada por TTL retorna None aunque el cache subyacente responda."""
        mock_cache = MagicMock()
        old_ts = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
        mock_cache.get.return_value = {
            "response": "stale data",
            "timestamp": old_ts,
        }
        # TTL de 1 segundo — la entrada de 2020 esta vencida
        shaped = ShapedCache(mock_cache, ttl_sec=1.0)

        result = shaped.get_shaped("stale prompt")

        assert result is None, "Entrada expirada debe retornar None"
        assert shaped._hit_count == 1  # Se cuenta como hit antes de verificar TTL
        assert shaped._miss_count == 0

    def test_shaped_cache_lru_eviction(self):
        """LRU eviction remueve las entradas mas viejas cuando se excede max_tokens."""
        mock_cache = MagicMock()
        mock_cache.set.return_value = True
        # Poblamos _entries para que el sum() en set_shaped tenga datos
        mock_cache._entries = {
            "hash_a": {"token_cost": 300},
            "hash_b": {"token_cost": 400},
        }

        shaped = ShapedCache(mock_cache, max_tokens=100)

        # Poblar LRU con entradas previas (orden de insercion = orden LRU)
        shaped._lru["hash_a"] = 1000.0
        shaped._lru["hash_b"] = 2000.0

        # Esta llamada supera max_tokens y dispara LRU eviction
        shaped.set_shaped("new prompt", "new response", token_cost=500)

        # Se debe haber eliminado al menos hash_a (el mas viejo)
        assert "hash_a" not in shaped._lru, "hash_a debe ser evictado"
        mock_cache.delete.assert_any_call("hash_a")
        assert shaped._cache.delete.call_count >= 1

    def test_shaped_cache_clear_expired(self):
        """clear_expired elimina solo entradas cuyo TTL haya vencido."""
        mock_cache = MagicMock()
        shaped = ShapedCache(mock_cache, ttl_sec=1.0)

        now = datetime.now(timezone.utc).timestamp()
        old_ts = now - 100.0  # muy vencida

        # Dos entradas vencidas + una reciente
        shaped._lru["old_entry_1"] = old_ts
        shaped._lru["old_entry_2"] = old_ts - 50.0
        shaped._lru["fresh_entry"] = now

        removed = shaped.clear_expired()

        assert removed == 2
        assert "old_entry_1" not in shaped._lru
        assert "old_entry_2" not in shaped._lru
        assert "fresh_entry" in shaped._lru
        assert mock_cache.delete.call_count == 2
        mock_cache.delete.assert_any_call("old_entry_1")
        mock_cache.delete.assert_any_call("old_entry_2")

    def test_shaped_cache_get_stats(self):
        """get_stats retorna dict completo con hit_rate, hits, misses, lru_size, max_tokens, ttl_sec."""
        mock_cache = MagicMock()
        shaped = ShapedCache(mock_cache)

        # Simular actividad
        shaped._hit_count = 4
        shaped._miss_count = 1
        shaped._lru["k1"] = 1000.0
        shaped._lru["k2"] = 2000.0
        shaped._lru["k3"] = 3000.0

        stats = shaped.get_stats()

        assert stats["hit_rate"] == 4 / 5  # 0.8
        assert stats["hits"] == 4
        assert stats["misses"] == 1
        assert stats["lru_size"] == 3
        assert stats["max_tokens"] == 10000
        assert stats["ttl_sec"] == 3600.0


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
    def test_deterministic(self):
        """Same input produces same embedding (deterministic)."""
        v1 = SemanticCache._default_embedding("hello")
        v2 = SemanticCache._default_embedding("hello")
        assert np.allclose(v1, v2)

    def test_different_inputs_different_vectors(self):
        """Different inputs produce different vectors (discriminative)."""
        v1 = SemanticCache._default_embedding("hello")
        v2 = SemanticCache._default_embedding("world")
        assert not np.allclose(v1, v2)

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
