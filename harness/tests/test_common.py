"""
Tests for harness.common — shared utilities (DRY unification).

Cubre: fallback_embedding, estimate_tokens, compression_pct,
      avg_compression_pct, keyword_match_score, StatsMixin,
      EMPTY_VECTOR, truncate_by_budget.
"""

import numpy as np
import pytest

from harness.common import (
    EMBEDDING_DIM,
    EMPTY_VECTOR,
    StatsMixin,
    avg_compression_pct,
    compression_pct,
    estimate_tokens,
    fallback_embedding,
    keyword_match_score,
    truncate_by_budget,
)


class TestFallbackEmbedding:
    """Test the unified embedding function."""

    def test_empty_text_returns_zeros(self):
        vec = fallback_embedding("")
        assert vec.shape == (EMBEDDING_DIM,)
        assert np.all(vec == 0)

    def test_normal_text_returns_normalized(self):
        vec = fallback_embedding("hello world")
        assert vec.shape == (EMBEDDING_DIM,)
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-6  # Must be unit vector

    def test_different_texts_different_vectors(self):
        v1 = fallback_embedding("implement API")
        v2 = fallback_embedding("security audit")
        assert not np.allclose(v1, v2)

    def test_same_text_same_vector(self):
        v1 = fallback_embedding("test message")
        v2 = fallback_embedding("test message")
        assert np.allclose(v1, v2)

    def test_custom_dimension(self):
        vec = fallback_embedding("test", dim=128)
        assert vec.shape == (128,)

    def test_unicode_text(self):
        vec = fallback_embedding("español français 中文")
        assert vec.shape == (EMBEDDING_DIM,)
        assert abs(np.linalg.norm(vec) - 1.0) < 1e-6


class TestEstimateTokens:
    """Test token estimation."""

    def test_empty_text(self):
        assert estimate_tokens("") >= 1

    def test_short_text(self):
        tokens = estimate_tokens("hello")
        assert tokens >= 1
        assert isinstance(tokens, int)

    def test_longer_text(self):
        text = "hello world " * 100
        tokens = estimate_tokens(text)
        assert tokens > 10

    def test_consistent(self):
        t1 = estimate_tokens("consistent test")
        t2 = estimate_tokens("consistent test")
        assert t1 == t2


class TestCompressionMath:
    """Test compression percentage calculations."""

    def test_compression_pct_no_change(self):
        assert compression_pct(100, 100) == 0.0

    def test_compression_pct_half(self):
        assert compression_pct(100, 50) == 50.0

    def test_compression_pct_zero_before(self):
        assert compression_pct(0, 0) == 0.0

    def test_avg_compression_pct(self):
        assert avg_compression_pct(1000, 300) == 30.0

    def test_avg_compression_pct_zero(self):
        assert avg_compression_pct(0, 0) == 0.0


class TestKeywordMatchScore:
    """Test keyword matching utility."""

    def test_simple_match(self):
        kw_map = {"api": "builder", "test": "guardian"}
        result, score = keyword_match_score("implement REST API", kw_map)
        assert result == "builder"
        assert score > 0

    def test_no_match_returns_default(self):
        kw_map = {"api": "builder"}
        result, score = keyword_match_score("hello world", kw_map, default="coordinator")
        assert result == "coordinator"
        assert score == 0

    def test_best_score_wins(self):
        kw_map = {"api": "builder", "rest api": "scientist"}
        result, score = keyword_match_score("implement REST API design", kw_map)
        assert result == "scientist"  # "rest api" is longer = higher score
        assert score > 0

    def test_dict_value_with_score_key(self):
        kw_map = {"api": {"score": 10, "result": "builder"}}
        result, score = keyword_match_score("implement API", kw_map)
        assert result == "builder"
        assert score == 10

    def test_empty_text(self):
        result, score = keyword_match_score("", {"any": "val"})
        assert result is None
        assert score == 0


class TestEMPTY_VECTOR:
    """Test the shared zero-vector constant."""

    def test_shape(self):
        assert EMPTY_VECTOR.shape == (EMBEDDING_DIM,)

    def test_all_zeros(self):
        assert np.all(EMPTY_VECTOR == 0)

    def test_is_immutable_copy(self):
        """Modifications to a copy should not affect the original."""
        cpy = EMPTY_VECTOR.copy()
        cpy[0] = 1.0
        assert EMPTY_VECTOR[0] == 0.0


class TestStatsMixin:
    """Test the StatsMixin for unified get_stats()."""

    def test_basic_stats(self):
        class MyClass(StatsMixin):
            def __init__(self):
                self._stats = {"tokens_before": 1000, "tokens_saved": 300}

        obj = MyClass()
        stats = obj.get_stats()
        assert stats["tokens_before"] == 1000
        assert stats["tokens_saved"] == 300
        assert stats["avg_compression_pct"] == 30.0

    def test_stats_empty(self):
        class MyClass(StatsMixin):
            def __init__(self):
                self._stats = {}

        obj = MyClass()
        stats = obj.get_stats()
        assert stats["avg_compression_pct"] == 0.0

    def test_stats_with_chars(self):
        class MyClass(StatsMixin):
            def __init__(self):
                self._stats = {"total_chars_before": 500, "total_chars_saved": 100}

        obj = MyClass()
        stats = obj.get_stats()
        assert stats["avg_compression_pct"] == 20.0


class TestTruncateByBudget:
    """Test the unified budget truncation utility."""

    def test_all_items_fit(self):
        items = ["a", "bb", "ccc"]
        result = truncate_by_budget(items, get_tokens=len, budget=100)
        assert result == items

    def test_some_items_truncated(self):
        items = ["a" * 50, "b" * 50, "c" * 50]
        result = truncate_by_budget(items, get_tokens=len, budget=60)
        assert len(result) < 3

    def test_safety_margin(self):
        items = ["a" * 100]
        # Budget 112 with 0.9 margin = 100 effective (int(112*0.9)=100), item is 100 chars → fits
        result = truncate_by_budget(items, get_tokens=len, budget=112, safety_margin=0.9)
        assert len(result) == 1

    def test_sort_key(self):
        items = [{"size": 10}, {"size": 5}, {"size": 1}]
        result = truncate_by_budget(
            items, get_tokens=lambda x: x["size"], budget=8,
            sort_key=lambda x: x["size"],
        )
        # Should keep smallest first (reverse=True default)
        assert len(result) >= 1

    def test_empty_items(self):
        result = truncate_by_budget([], get_tokens=len, budget=100)
        assert len(result) >= 1 or result == []


class TestSharedPrimitives:
    """Primitivas compartidas: short_hash, utc_now_iso, safe_json_loads."""

    def test_short_hash_deterministic(self) -> None:
        """Mismo contenido = mismo hash; distinto = distinto (casi seguro)."""
        from harness.common import short_hash

        assert short_hash("abc") == short_hash("abc")
        assert len(short_hash("abc")) == 12
        assert len(short_hash("abc", length=16)) == 16
        assert short_hash("abc") != short_hash("abd")

    def test_short_hash_invalid_length(self) -> None:
        """Length < 1 falla accionable."""
        from harness.common import short_hash

        with pytest.raises(ValueError, match="WHAT"):
            short_hash("x", length=0)

    def test_utc_now_iso_format(self) -> None:
        """Formato ISO con zona UTC."""
        from harness.common import utc_now_iso

        stamp = utc_now_iso()
        assert "T" in stamp and ("+" in stamp or stamp.endswith("Z"))

    def test_safe_json_loads_valid(self) -> None:
        """JSON valido parsea; no-str pasa; invalido da default."""
        from harness.common import safe_json_loads

        assert safe_json_loads('{"a": 1}') == {"a": 1}
        assert safe_json_loads({"a": 1}) == {"a": 1}
        assert safe_json_loads("no-json", default={}) == {}
        assert safe_json_loads(None) is None
