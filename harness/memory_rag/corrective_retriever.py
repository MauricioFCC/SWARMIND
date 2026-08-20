"""corrective_retriever.py — CRAG: validacion de recuperacion previa a generacion.

Implementa la arquitectura **Corrective RAG (CRAG)** (Yan et al., arXiv:2401.15884):
antes de inyectar contexto al LLM, valida la calidad de la recuperacion.
Si es pobre, aplica acciones correctivas: reescritura de query (query
rewrite) o caida a una fuente alternativa de recuperacion (fallback),
mejorando la fiabilidad del sistema a costa de un paso adicional de evaluacion.

Referencia: "Corrective Retrieval Augmented Generation" (arXiv:2401.15884)
y patron CRAG 2026: evaluador ligero de relevancia + accion correctiva.

Uso:
    crag = CorrectiveRetriever(primary=hybrid, fallback=fts, evaluator=...)
    results, action = crag.retrieve("query", top_k=5)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
# Umbral de score normalizado: por debajo, la recuperacion se considera pobre
_LOW_QUALITY_THRESHOLD = 0.30
# Fraccion minima de terminos de la query que deben aparecer en los resultados
_MIN_QUERY_COVERAGE = 0.40
# Acciones correctivas posibles
_ACTION_NONE = "none"
_ACTION_REWRITE = "rewrite"
_ACTION_FALLBACK = "fallback"
# Terminos vacios de la query que no aportan senal
_STOPWORDS = {"el", "la", "los", "las", "de", "del", "para", "con", "que", "y"}


class RetrievalSource(Protocol):
    """Contrato de una fuente de recuperacion (vector, fts, hibrido)."""

    def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class CorrectiveResult:
    """Resultado de la recuperacion correctiva.

    Attributes:
        items: Resultados recuperados (dicts con id/score/metadata).
        action: Accion aplicada (none/rewrite/fallback).
        quality_score: Score de calidad de la recuperacion [0, 1].
        corrected_query: Query usada (original o reescrita).
    """

    items: list[dict[str, Any]]
    action: str
    quality_score: float
    corrected_query: str


class CorrectiveRetriever:
    """Retriever correctivo que valida y corrige la recuperacion.

    Args:
        primary: Fuente principal de recuperacion (hibrido recomendado).
        fallback: Fuente alternativa para el fallback (BM25 recomendado).
        evaluator: Funcion (query, results) -> score de calidad [0, 1].
            Si es None, se usa el evaluador heuristico interno.
        rewrite_fn: Funcion de reescritura de query (query -> query).
            Si es None, se usa la expansion de keywords interna.
    """

    def __init__(
        self,
        primary: RetrievalSource,
        fallback: RetrievalSource,
        evaluator: Callable[[str, list[dict[str, Any]]], float] | None = None,
        rewrite_fn: Callable[[str], str] | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._evaluator = evaluator or self._heuristic_evaluate
        self._rewrite_fn = rewrite_fn or self._expand_query

    def retrieve(self, query: str, top_k: int = 5) -> CorrectiveResult:
        """Recupera validando calidad y aplicando correcciones si es pobre.

        Flujo CRAG: (1) recupera con la fuente primaria, (2) evalua la
        calidad del contexto, (3) si es pobre, reescribe la query y
        reintenta, (4) si sigue pobre, cae a la fuente alternativa.

        Args:
            query: Consulta del usuario.
            top_k: Maximo de resultados.

        Returns:
            CorrectiveResult con items, accion, calidad y query usada.
        """
        items = self._primary.retrieve(query, top_k=top_k)
        quality = self._evaluator(query, items)
        if quality >= _LOW_QUALITY_THRESHOLD:
            return CorrectiveResult(
                items=items, action=_ACTION_NONE,
                quality_score=quality, corrected_query=query,
            )
        rewritten = self._rewrite_fn(query)
        rewritten_items = self._primary.retrieve(rewritten, top_k=top_k)
        rewritten_quality = self._evaluator(query, rewritten_items)
        if rewritten_quality > quality:
            return CorrectiveResult(
                items=rewritten_items, action=_ACTION_REWRITE,
                quality_score=rewritten_quality, corrected_query=rewritten,
            )
        fallback_items = self._fallback.retrieve(query, top_k=top_k)
        fallback_quality = self._evaluator(query, fallback_items)
        return CorrectiveResult(
            items=fallback_items or items, action=_ACTION_FALLBACK,
            quality_score=fallback_quality, corrected_query=query,
        )

    # ------------------------------------------------------------------
    # Evaluador y reescritura heuristica (cero LLM, determinista)
    # ------------------------------------------------------------------

    @staticmethod
    def _heuristic_evaluate(query: str, items: list[dict[str, Any]]) -> float:
        """Evalua la calidad de la recuperacion sin LLM.

        Combina dos senales: (1) el score medio normalizado de los
        resultados (relevancia) y (2) la cobertura de terminos de la
        query en el contenido recuperado (exhaustividad).

        Args:
            query: Consulta original.
            items: Resultados recuperados.

        Returns:
            Score de calidad en [0, 1].
        """
        if not items:
            return 0.0
        mean_score = sum(float(item.get("score", 0.0)) for item in items) / len(items)
        norm_score = max(0.0, min(1.0, mean_score))
        terms = [t for t in query.lower().split() if t not in _STOPWORDS and len(t) > 2]
        if not terms:
            return norm_score
        corpus = " ".join(
            str(item.get("content", ""))
            + " "
            + str(item.get("metadata", {}).get("chunk", ""))
            for item in items
        ).lower()
        covered = sum(1 for term in terms if term in corpus)
        coverage = covered / len(terms)
        return min(1.0, 0.6 * norm_score + 0.4 * coverage)

    @staticmethod
    def _expand_query(query: str) -> str:
        """Reescritura por expansion de keywords (query rewrite ligero).

        Duplica los terminos significativos de la query para reforzar la
        coincidencia lexical en BM25/FTS, sin invocar al LLM.

        Args:
            query: Consulta original.

        Returns:
            Query expandida con terminos clave duplicados.
        """
        terms = [t for t in query.split() if t.lower() not in _STOPWORDS and len(t) > 2]
        if not terms:
            return query
        return query + " " + " ".join(terms)