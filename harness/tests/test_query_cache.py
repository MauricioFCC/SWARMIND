"""Tests para QueryResultCache (TTL, invalidacion y contadores de uso)."""

from __future__ import annotations

import harness.memory_rag.query_cache as cache_module
from harness.memory_rag.query_cache import QueryResultCache


def test_set_then_get_is_hit() -> None:
    """Una entrada vigente se sirve y cuenta como hit."""
    cache = QueryResultCache(ttl_sec=60.0)
    cache.set("SELECT 1", "rows", collection="a")

    assert cache.get("SELECT 1") == "rows"
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 0
    assert stats["entries"] == 1


def test_unknown_key_is_miss() -> None:
    """Un miss devuelve None y no inventa hits."""
    cache = QueryResultCache()

    assert cache.get("SELECT 2") is None
    stats = cache.stats()
    assert stats["misses"] == 1
    assert stats["expired"] == 0


def test_expired_entry_counts_as_expired_and_miss(monkeypatch) -> None:
    """Al vencer el TTL la entrada se descarta y se contabiliza."""
    clock = {"now": 1000.0}
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: clock["now"])
    cache = QueryResultCache(ttl_sec=10.0)
    cache.set("SELECT 3", "rows")
    clock["now"] += 11.0

    assert cache.get("SELECT 3") is None
    stats = cache.stats()
    assert stats["expired"] == 1
    assert stats["misses"] == 1
    assert stats["hits"] == 0
    assert stats["entries"] == 0


def test_invalidate_only_removes_target_collection() -> None:
    """La invalidacion por coleccion no toca otras entradas."""
    cache = QueryResultCache()
    cache.set("q1", "a", collection="col")
    cache.set("q2", "b", collection="otra")

    assert cache.invalidate("col") == 1
    assert cache.get("q1") is None
    assert cache.get("q2") == "b"
