"""test_corrective_retriever.py — Tests del CRAG (Corrective RAG)."""

from __future__ import annotations

from typing import Any

import pytest

from harness.memory_rag.corrective_retriever import (
    _LOW_QUALITY_THRESHOLD,
    CorrectiveResult,
    CorrectiveRetriever,
)


class FakeSource:
    """Fuente de recuperacion fake con resultados configurados."""

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = results
        self.calls: list[str] = []

    def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        self.calls.append(query)
        return self._results[:top_k]


def _good_items() -> list[dict[str, Any]]:
    """Items de alta calidad (score alto + contenido relevante)."""
    return [
        {
            "id": "doc_1",
            "score": 0.85,
            "content": "threat modeling OWASP security auditoria",
            "metadata": {"chunk": "seguridad OWASP"},
        },
        {
            "id": "doc_2",
            "score": 0.80,
            "content": "auditoria de seguridad de aplicaciones web",
            "metadata": {"chunk": "auditoria"},
        },
    ]


def _poor_items() -> list[dict[str, Any]]:
    """Items de baja calidad (score bajo, sin coincidencia lexical)."""
    return [
        {
            "id": "doc_x",
            "score": 0.10,
            "content": "recetas de cocina italiana",
            "metadata": {"chunk": "cocina"},
        },
    ]


def test_retrieve_returns_none_action_on_good_quality() -> None:
    """Calidad buena -> accion none, sin reescritura."""
    primary = FakeSource(_good_items())
    fallback = FakeSource(_poor_items())
    crag = CorrectiveRetriever(primary=primary, fallback=fallback)
    result = crag.retrieve("auditoria de seguridad OWASP")
    assert result.action == "none"
    assert result.quality_score >= _LOW_QUALITY_THRESHOLD
    assert result.corrected_query == "auditoria de seguridad OWASP"
    assert len(primary.calls) == 1


def test_retrieve_rewrites_on_poor_quality() -> None:
    """Calidad pobre -> rewrite que mejora la calidad."""
    # Fuente que devuelve items pobres con la query original y items
    # buenos tras la reescritura (simula que el rewrite mejora la busqueda).
    class ImprovingSource(FakeSource):
        def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
            self.calls.append(query)
            if "rewritten" in query:
                return _good_items()[:top_k]
            return _poor_items()[:top_k]

    primary = ImprovingSource([])
    fallback = FakeSource(_poor_items())

    def evaluator(query: str, items: list[dict[str, Any]]) -> float:
        return 0.9 if any(item.get("id") == "doc_1" for item in items) else 0.1

    crag = CorrectiveRetriever(
        primary=primary,
        fallback=fallback,
        evaluator=evaluator,
        rewrite_fn=lambda query: "rewritten " + query,
    )
    result = crag.retrieve("seguridad")
    assert result.action == "rewrite"
    assert result.corrected_query.startswith("rewritten")
    assert result.quality_score == pytest.approx(0.9)


def test_retrieve_falls_back_when_rewrite_does_not_improve() -> None:
    """Rewrite sin mejora -> fallback a fuente alternativa."""
    primary = FakeSource(_poor_items())
    fallback = FakeSource(_good_items())
    crag = CorrectiveRetriever(
        primary=primary,
        fallback=fallback,
        evaluator=lambda query, items: 0.1,  # siempre pobre
        rewrite_fn=lambda query: query,       # rewrite no mejora
    )
    result = crag.retrieve("seguridad")
    assert result.action == "fallback"
    assert result.items[0]["id"] == "doc_1"
    assert result.quality_score == pytest.approx(0.1)


def test_retrieve_empty_items_quality_zero() -> None:
    """Sin resultados -> calidad 0 -> accion correctiva."""
    primary = FakeSource([])
    fallback = FakeSource(_good_items())
    crag = CorrectiveRetriever(
        primary=primary,
        fallback=fallback,
        evaluator=lambda query, items: 0.0,
        rewrite_fn=lambda query: query,
    )
    result = crag.retrieve("algo")
    assert result.action == "fallback"


def test_heuristic_evaluate_empty() -> None:
    """Evaluador heuristico: sin items -> 0."""
    score = CorrectiveRetriever._heuristic_evaluate("query", [])
    assert score == 0.0


def test_heuristic_evaluate_high_coverage() -> None:
    """Evaluador heuristico: cobertura alta de terminos -> score alto."""
    score = CorrectiveRetriever._heuristic_evaluate(
        "seguridad auditoria", _good_items()
    )
    assert score > 0.5


def test_heuristic_evaluate_low_coverage() -> None:
    """Evaluador heuristico: sin cobertura de terminos -> score bajo."""
    score = CorrectiveRetriever._heuristic_evaluate(
        "seguridad auditoria", _poor_items()
    )
    assert score < 0.5


def test_heuristic_evaluate_stopwords_only() -> None:
    """Solo stopwords en la query -> usa score medio normalizado."""
    items = [{"id": "a", "score": 0.8, "content": "x"}]
    score = CorrectiveRetriever._heuristic_evaluate("el la de", items)
    assert score == pytest.approx(0.8)


def test_expand_query_duplicates_terms() -> None:
    """Expansion duplica terminos significativos."""
    expanded = CorrectiveRetriever._expand_query("auditoria de seguridad")
    assert "auditoria" in expanded
    assert "seguridad" in expanded
    assert expanded.count("auditoria") == 2


def test_expand_query_only_stopwords_returns_original() -> None:
    """Query solo con stopwords -> se devuelve intacta."""
    assert CorrectiveRetriever._expand_query("el la de") == "el la de"


def test_corrective_result_dataclass() -> None:
    """CorrectiveResult es una dataclass con los campos esperados."""
    result = CorrectiveResult(
        items=[], action="none", quality_score=0.7, corrected_query="q"
    )
    assert result.action == "none"
    assert result.quality_score == pytest.approx(0.7)
    assert result.corrected_query == "q"