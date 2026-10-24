"""Adaptive retrieval (frontier: arXiv:2403.14403) sobre RuscaDB/SWARMIND.

Selecciona dinamicamente la estrategia de retrieval (none/sparse/dense/hybrid/iterative)
segun la complejidad de la consulta, evitando overhead en queries simples y
cubriendo multi-step en queries complejas.
"""

from __future__ import annotations

import logging
from typing import Any

from harness.memory_rag.hybrid_retriever import HybridResult, HybridRetriever

logger = logging.getLogger("harness.memory_rag.adaptive_retriever")

# Heuristicas de complejidad (sin LLM, deterministas)
_COMPLEX_KEYWORDS = ("compara", "analiza", "explica", "por que", "como", "diferencia", "relacion", "causa", "consecuencia", "paso a paso")
_MULTI_STEP_KEYWORDS = (" y ", " luego ", " despues ", " ademas ", " tambien ", " primero ", " segundo ")


def classify_complexity(query: str) -> str:
    """Clasifica la complejidad de una consulta: 'simple', 'medium', 'complex'."""
    q = query.strip().lower()
    if not q:
        return "simple"
    words = q.split()
    n = len(words)
    has_complex = any(k in q for k in _COMPLEX_KEYWORDS)
    has_multi = any(k in q for k in _MULTI_STEP_KEYWORDS)
    if n <= 4 and not has_complex and not has_multi:
        return "simple"
    if has_multi or (has_complex and n > 8):
        return "complex"
    return "medium"


class AdaptiveRetriever:
    """Retriever adaptativo que selecciona estrategia segun complejidad."""

    def __init__(self, hybrid: HybridRetriever, embed_fn: Any = None) -> None:
        self._hybrid = hybrid
        self._embed_fn = embed_fn

    def retrieve(self, query: str, top_k: int = 5) -> list[HybridResult]:
        level = classify_complexity(query)
        if level == "simple":
            # Solo sparse (FTS) — evita overhead de embeddings
            try:
                sparse = self._hybrid._sparse_retrieve(query, top_k)
            except Exception:  # noqa: BLE001
                sparse = []
            fused = self._hybrid._fuse([], sparse)
            return sorted(fused, key=lambda x: x.score, reverse=True)[:top_k]
        if level == "medium":
            return self._hybrid.retrieve(query, top_k=top_k)
        # complex: iterative (2 rounds)
        results = self._hybrid.retrieve(query, top_k=top_k)
        # segundo round: refinar con los top resultados como contexto
        try:
            refined_query = query + " " + " ".join(r.doc_id for r in results[:2])
            results2 = self._hybrid.retrieve(refined_query, top_k=top_k)
            # fusionar dedupe
            seen = {r.doc_id for r in results}
            for r in results2:
                if r.doc_id not in seen:
                    results.append(r)
                    seen.add(r.doc_id)
        except Exception:  # noqa: BLE001, S110
            pass
        return sorted(results, key=lambda x: x.score, reverse=True)[:top_k]