"""Tests para AdaptiveRetriever (frontier: arXiv:2403.14403)."""

from __future__ import annotations

from unittest.mock import MagicMock

from harness.memory_rag.adaptive_retriever import AdaptiveRetriever, classify_complexity


def test_classify_complexity():
    assert classify_complexity("hola") == "simple"
    assert classify_complexity("que es python") == "simple"
    assert classify_complexity("explica como funciona el sistema de memoria") == "medium"
    assert classify_complexity("analiza la diferencia entre A y B y luego explica por que") == "complex"
    assert classify_complexity("") == "simple"


def test_adaptive_simple_uses_sparse():
    hybrid = MagicMock()
    hybrid._sparse_retrieve.return_value = [{"id": "1", "score": 0.5}]
    hybrid._fuse.return_value = []
    ar = AdaptiveRetriever(hybrid)
    res = ar.retrieve("hola", top_k=3)
    assert isinstance(res, list)
    hybrid._sparse_retrieve.assert_called()


def test_adaptive_medium_uses_hybrid():
    hybrid = MagicMock()
    hybrid.retrieve.return_value = []
    ar = AdaptiveRetriever(hybrid)
    ar.retrieve("explica python", top_k=3)
    hybrid.retrieve.assert_called()


def test_adaptive_complex_iterative():
    hybrid = MagicMock()
    hybrid.retrieve.return_value = [MagicMock(doc_id="d1", score=0.9)]
    ar = AdaptiveRetriever(hybrid)
    res = ar.retrieve("analiza la diferencia entre A y B y luego explica por que", top_k=3)
    assert isinstance(res, list)
    assert hybrid.retrieve.call_count >= 1