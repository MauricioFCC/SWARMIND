"""ColBERT-style reranking (MaxSim) para SWARMIND.

Spec: docs/specs/ruscadb-colbert-rerank.md.
Implementacion ligera basada en token-overlap MaxSim (sin modelo ONNX).
"""

from __future__ import annotations

from typing import Any


def _tokens(text: str) -> list[str]:
    return [t for t in text.lower().split() if t]


def maxsim_score(query: str, doc: str) -> float:
    """Score MaxSim simplificado: suma de max cosine por token de query.

    Args:
        query: Consulta.
        doc: Documento.

    Returns:
        Score (mayor = mas relevante).
    """
    q_tokens = _tokens(query)
    d_tokens = _tokens(doc)
    if not q_tokens or not d_tokens:
        return 0.0
    # similitud por igualdad de token (proxy de cosine)
    total = 0.0
    for qt in q_tokens:
        best = 0.0
        for dt in d_tokens:
            if qt == dt:
                best = 1.0
                break
            # similitud parcial por prefijo
            if qt.startswith(dt) or dt.startswith(qt):
                best = max(best, 0.5)
        total += best
    return total / len(q_tokens)


def rerank(query: str, candidates: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
    """Rerankea candidatos por MaxSim.

    Args:
        query: Consulta.
        candidates: Lista de dicts con 'text' o 'metadata'.
        top_k: Numero de resultados.

    Returns:
        Lista rerankeada con campo 'rerank_score'.
    """
    scored = []
    for c in candidates:
        text = c.get("text") or ""
        if not text:
            meta = c.get("metadata") or {}
            text = str(meta.get("text", "") or meta.get("summary", "") or "")
        s = maxsim_score(query, text)
        entry = dict(c)
        entry["rerank_score"] = s
        scored.append(entry)
    scored.sort(key=lambda x: x["rerank_score"], reverse=True)
    return scored[:top_k]


__all__ = ["maxsim_score", "rerank"]
