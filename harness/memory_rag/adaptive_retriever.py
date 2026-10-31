"""Adaptive retrieval (frontier: arXiv:2403.14403) sobre RuscaDB/SWARMIND.

Selecciona dinamicamente la estrategia de retrieval (none/sparse/dense/hybrid/iterative)
segun la complejidad de la consulta, evitando overhead en queries simples y
cubriendo multi-step en queries complejas.
"""

from __future__ import annotations

import logging
from typing import Any

from harness.memory_rag.hybrid_retriever import HybridResult

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


class _StoreAdapter:
    """Adapta un RuscaDBStore (o cualquier store con hybrid_search) al
    contrato minimo que espera ``AdaptiveRetriever`` (retrieve/_sparse_retrieve/_fuse)."""

    def __init__(self, store: Any, collection: str = "memory") -> None:
        self._store = store
        self._collection = collection

    def retrieve(self, query: str, top_k: int = 5) -> list[HybridResult]:
        try:
            rows = self._store.hybrid_search(self._collection, [], query, top_k=top_k)
        except Exception:  # noqa: BLE001
            try:
                rows = self._store.full_text_search(self._collection, query, top_k=top_k)
            except Exception:  # noqa: BLE001
                rows = []
        out: list[HybridResult] = []
        for i, r in enumerate(rows or []):
            doc_id = str(r.get("id") or r.get("doc_id") or i)
            out.append(HybridResult(doc_id=doc_id, score=float(r.get("score", 1.0 / (i + 1))), metadata=r))
        return out

    def _sparse_retrieve(self, query: str, top_k: int) -> list[dict[str, Any]]:
        try:
            return self._store.full_text_search(self._collection, query, top_k=top_k) or []
        except Exception:  # noqa: BLE001
            return []

    def _fuse(self, dense: list[Any], sparse: list[Any]) -> list[HybridResult]:
        # Fusion RRF minima para el path 'simple'.
        out: list[HybridResult] = []
        seen: set[str] = set()
        for i, r in enumerate(sparse or []):
            doc_id = str(r.get("id") or r.get("doc_id") or i)
            if doc_id in seen:
                continue
            seen.add(doc_id)
            out.append(HybridResult(doc_id=doc_id, score=1.0 / (i + 1), sparse_rank=i + 1, metadata=r))
        return out


class AdaptiveRetriever:
    """Retriever adaptativo que selecciona estrategia segun complejidad."""

    def __init__(self, hybrid: Any, embed_fn: Any = None) -> None:
        # Aceptar HybridRetriever, _StoreAdapter, o un store con hybrid_search.
        if hasattr(hybrid, "hybrid_search") and not hasattr(hybrid, "retrieve"):
            hybrid = _StoreAdapter(hybrid)
        self._hybrid = hybrid
        self._embed_fn = embed_fn

    @classmethod
    def from_store(cls, store: Any, collection: str = "memory", embed_fn: Any = None) -> AdaptiveRetriever:
        """Construye un AdaptiveRetriever sobre un store RuscaDB/Lance."""
        return cls(_StoreAdapter(store, collection=collection), embed_fn=embed_fn)

    def retrieve(self, query: str, top_k: int = 5) -> list[HybridResult]:
        level = classify_complexity(query)
        if level == "simple":
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
        try:
            refined_query = query + " " + " ".join(r.doc_id for r in results[:2])
            results2 = self._hybrid.retrieve(refined_query, top_k=top_k)
            seen = {r.doc_id for r in results}
            for r in results2:
                if r.doc_id not in seen:
                    results.append(r)
                    seen.add(r.doc_id)
        except Exception:  # noqa: BLE001, S110
            pass
        return sorted(results, key=lambda x: x.score, reverse=True)[:top_k]


__all__ = ["AdaptiveRetriever", "_StoreAdapter", "classify_complexity"]
