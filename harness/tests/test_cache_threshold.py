"""Tests del umbral adaptativo del cache semantico (vCache, ICLR 2026)."""

from __future__ import annotations

import pytest

from harness.memory_rag.cache_threshold import (
    THRESHOLD_KEY_PREFIX,
    THRESHOLD_KIND,
    AdaptiveThreshold,
)
from harness.memory_rag.ruscadb_store import RuscaDBStore
from harness.memory_rag.semantic_cache import SemanticCache

try:
    from harness.memory_rag.ruscadb import load_library

    load_library()
    _RUSCADB_AVAILABLE = True
except Exception:  # noqa: BLE001
    _RUSCADB_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _RUSCADB_AVAILABLE, reason="RuscaDB C-ABI dll not available"
)


@pytest.fixture
def store(tmp_path):
    """Store RuscaDB aislado por test."""
    s = RuscaDBStore(db_path=str(tmp_path / "thr.db"))
    yield s
    s.close()


def test_threshold_starts_at_base():
    """Sin observaciones el umbral es el base."""
    learner = AdaptiveThreshold(base=0.92)
    assert learner.threshold_for("un prompt cualquiera") == 0.92


def test_false_positive_raises_threshold():
    """Un hit incorrecto sube el umbral (exigir mas similitud)."""
    learner = AdaptiveThreshold(base=0.92, step=0.01)
    updated = learner.observe("prompt A", correct=False)
    assert updated == pytest.approx(0.93)
    assert learner.threshold_for("prompt A") == pytest.approx(0.93)


def test_correct_hit_lowers_threshold_with_floor():
    """Un acierto baja el umbral sin cruzar el piso."""
    learner = AdaptiveThreshold(base=0.905, min_threshold=0.90, step=0.01)
    assert learner.observe("prompt B", correct=True) == pytest.approx(0.90)
    assert learner.observe("prompt B", correct=True) == pytest.approx(0.90)


def test_threshold_is_clamped_to_ceiling():
    """El aprendizaje no supera el techo configurado."""
    learner = AdaptiveThreshold(base=0.92, max_threshold=0.93, step=0.05)
    assert learner.observe("prompt C", correct=False) == pytest.approx(0.93)


def test_buckets_are_per_prompt_family():
    """Prompts con el mismo prefijo comparten umbral; otros no."""
    learner = AdaptiveThreshold(base=0.92, step=0.01, prefix_chars=32)
    familia = "familia uno: instruccion comun " + "x" * 40
    learner.observe(familia + " pregunta A", correct=False)
    assert learner.threshold_for(familia + " pregunta B") > 0.92
    assert learner.threshold_for("familia dos: otra cosa") == pytest.approx(0.92)


def test_stats_summarize_learning():
    """stats resume cubos y rango."""
    learner = AdaptiveThreshold(base=0.92, step=0.01)
    learner.observe("a", correct=False)
    learner.observe("b", correct=True)
    stats = learner.stats()
    assert stats["buckets"] == 2
    assert stats["min"] <= stats["mean_threshold"] <= stats["max"]


def test_learning_persists_across_instances(store):
    """El umbral aprendido sobrevive a una nueva instancia (store persistente)."""
    first = AdaptiveThreshold(base=0.92, step=0.01, store=store)
    first.observe("prompt persistente", correct=False)
    key = f"{THRESHOLD_KEY_PREFIX}{first.bucket('prompt persistente')}"
    stored = store.semantic_cache_entries()
    assert any(item["id"] == key for item in stored)
    assert any(
        (item.get("metadata") or {}).get("kind") == THRESHOLD_KIND for item in stored
    )

    second = AdaptiveThreshold(base=0.92, step=0.01, store=store)
    assert second.threshold_for("prompt persistente") == pytest.approx(0.93)


def test_semantic_cache_raises_threshold_with_feedback(store):
    """SemanticCache(adaptive_threshold) aplica el umbral aprendido en get."""
    cache = SemanticCache(vector_store=store, adaptive_threshold=True)
    cache.set("p", "r")
    threshold = cache.record_feedback("p", correct=False)
    assert threshold > cache._threshold
    stats = cache.get_stats()
    assert stats["adaptive_threshold"] is True
    assert stats["adaptive"]["buckets"] == 1


def test_feedback_requires_adaptive_mode(store):
    """record_feedback sin modo adaptativo es un error de programacion."""
    cache = SemanticCache(vector_store=store)
    with pytest.raises(RuntimeError) as excinfo:
        cache.record_feedback("p", correct=True)
    assert "umbral_no_adaptativo" in str(excinfo.value)


def test_adaptive_threshold_filters_similarity_hits(store, monkeypatch):
    """Con umbral 1.01 ningun hit por similitud pasa; sin el, si."""
    cache = SemanticCache(vector_store=store, adaptive_threshold=True)
    cache.set("p", "r")
    key = cache._cache_key("p")
    # Quitar solo la fila persistente para forzar la ruta de similitud.
    store.execute(f"DELETE FROM semantic_cache WHERE id = '{key}'")
    assert cache.get("p") == "r"

    monkeypatch.setattr(cache._adaptive, "threshold_for", lambda _prompt: 1.01)
    assert cache.get("p") is None


def test_threshold_entries_not_invalidated_by_version(store):
    """El estado del umbral no se purga al invalidar una version de dataset."""
    cache = SemanticCache(
        vector_store=store, dataset_version="v1", adaptive_threshold=True
    )
    cache.record_feedback("p", correct=False)
    assert cache.invalidate_version() == 0
    assert store.semantic_cache_entries()
