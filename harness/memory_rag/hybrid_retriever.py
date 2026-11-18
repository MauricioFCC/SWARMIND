"""hybrid_retriever.py — RAG hibrido: fusion RRF de vector denso + BM25 disperso.

Implementa la arquitectura de RAG hibrido (2026): la busqueda semantica
densa (embeddings, LanceDB) y la coincidencia por palabras clave dispersa
(BM25, SQLite FTS) se complementan. La fusion se hace con **Reciprocal
Rank Fusion (RRF)**, que combina rankings sin depender de escalas de
score incompatibles entre motores.

Referencia: Cormack et al. 2009 (RRF) — estandar de facto en sistemas
de produccion híbridos 2026 (vector + BM25 + reranker).

Uso:
    fts = FTSSearch(db_path)
    vector = LanceVectorStore()
    hybrid = HybridRetriever(vector_store=vector, fts_search=fts, embed_fn=embed)
    results = hybrid.retrieve("query", top_k=5)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from harness.domain.ports import VectorStorePort
from harness.memory_rag.fts_search import FTSSearch

logger = logging.getLogger("harness.memory_rag.hybrid_retriever")

# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
# Constante de suavizado RRF (estandar de la literatura: 60)
_RRF_K = 60.0
# Coleccion por defecto del vector store
_DEFAULT_COLLECTION = "memory"
# Pesos de la fusion denso/disperso (complementarios, no excluyentes)
_DENSE_WEIGHT = 0.5
_SPARSE_WEIGHT = 0.5
# Pool de candidatos que entra al rerank (stage 2 de ColBERT: top-50).
_RERANK_POOL_FACTOR = 10
_RERANK_MIN_POOL = 50


@dataclass(frozen=True)
class HybridResult:
    """Resultado fusionado de la busqueda hibrida.

    Attributes:
        doc_id: Identificador unico del documento.
        score: Score RRF fusionado (mas alto = mas relevante).
        dense_rank: Posicion en el ranking denso (1-based, 0 si ausente).
        sparse_rank: Posicion en el ranking disperso (1-based, 0 si ausente).
        metadata: Metadatos del documento.
    """

    doc_id: str
    score: float
    dense_rank: int = 0
    sparse_rank: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


def _item_text(item: HybridResult) -> str:
    """Extrae el texto indexable de un resultado fusionado.

    Args:
        item: Resultado hibrido con metadata.

    Returns:
        Primer campo textual conocido, o cadena vacia.
    """
    meta = item.metadata or {}
    for key in ("text", "content", "summary", "title"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _validate_query(query: str, top_k: int) -> None:
    """Valida los argumentos de retrieval (fail-fast tipado).

    Args:
        query: Consulta del usuario.
        top_k: Numero de resultados pedidos.

    Raises:
        ValueError: Si top_k no es positivo o la query es vacia.
    """
    if top_k <= 0:
        raise ValueError(
            f"WHAT: top_k invalido: {top_k}"
            f"WHY: debe ser un entero positivo"
            f"WHERE: HybridRetriever.retrieve()"
        )
    if not query.strip():
        raise ValueError(
            "WHAT: query vacia"
            "WHY: no se puede recuperar sin texto de consulta"
            "WHERE: HybridRetriever.retrieve()"
        )


def _rerank_candidates(pool: list[HybridResult]) -> list[dict[str, Any]]:
    """Candidatos minimos que consume el reranker MaxSim.

    Args:
        pool: Resultados fusionados que entran al stage 2.

    Returns:
        Lista de ``{id, text, metadata}``.
    """
    return [
        {"id": item.doc_id, "text": _item_text(item), "metadata": item.metadata}
        for item in pool
    ]


def _rerank_results(
    scored: list[dict[str, Any]], pool: list[HybridResult]
) -> list[HybridResult]:
    """Reconstruye resultados con el score MaxSim, conservando los rangos RRF.

    Args:
        scored: Salida del reranker (``ID`` + ``rerank_score``).
        pool: Candidatos originales del stage 2.

    Returns:
        Lista de HybridResult en el orden del reranker.
    """
    by_id = {item.doc_id: item for item in pool}
    out: list[HybridResult] = []
    for entry in scored:
        base = by_id.get(str(entry.get("id")))
        if base is None:
            continue
        out.append(
            HybridResult(
                doc_id=base.doc_id,
                score=float(entry.get("rerank_score", 0.0)),
                dense_rank=base.dense_rank,
                sparse_rank=base.sparse_rank,
                metadata=base.metadata,
            )
        )
    return out


class HybridRetriever:
    """Retriever hibrido que fusiona vector denso y BM25 disperso con RRF.

    Args:
        vector_store: Almacen vectorial (LanceDB) con busqueda semantica.
        fts_search: Busqueda full-text (BM25 via SQLite FTS5).
        embed_fn: Funcion de embedding (texto -> vector).
        collection: Coleccion del vector store.
    """

    def __init__(
        self,
        vector_store: VectorStorePort,
        fts_search: FTSSearch,
        embed_fn: Callable[[str], np.ndarray],
        collection: str = _DEFAULT_COLLECTION,
    ) -> None:
        self._vector_store = vector_store
        self._fts_search = fts_search
        self._embed_fn = embed_fn
        self._collection = collection

    def retrieve(
        self, query: str, top_k: int = 5, rerank: bool = False
    ) -> list[HybridResult]:
        """Recupera documentos fusionando rankings denso y disperso (RRF).

        Args:
            query: Consulta del usuario.
            top_k: Maximo de resultados fusionados a devolver.
            rerank: Si True, reordena la cola del ranking con MaxSim de ColBERT
                (Spec ruscadb-colbert-rerank, stage 2).

        Returns:
            Lista de HybridResult ordenada por score descendente.

        Raises:
            ValueError: Si top_k no es positivo o la query es vacia.
        """
        _validate_query(query, top_k)
        dense_results = self._dense_retrieve(query, top_k)
        sparse_results = self._sparse_retrieve(query, top_k)
        fused = self._fuse(dense_results, sparse_results)
        ranked = sorted(fused, key=lambda item: item.score, reverse=True)
        if not rerank:
            return ranked[:top_k]
        return self._rerank(query, ranked, top_k)

    def _rerank(
        self, query: str, ranked: list[HybridResult], top_k: int
    ) -> list[HybridResult]:
        """Reordena la cola del ranking con MaxSim (stage 2 de ColBERT).

        Args:
            query: Consulta del usuario.
            ranked: Resultados ya fusionados por RRF.
            top_k: Resultados finales.

        Returns:
            Lista reordenada por ``rerank_score``; los empates conservan el
            orden RRF porque el ordenamiento de MaxSim es estable.
        """
        from harness.memory_rag.colbert_rerank import rerank as _maxsim

        pool = ranked[: max(top_k * _RERANK_POOL_FACTOR, _RERANK_MIN_POOL)]
        scored = _maxsim(query, _rerank_candidates(pool), top_k=top_k)
        return _rerank_results(scored, pool)

    async def aretrieve(
        self, query: str, top_k: int = 5, rerank: bool = False
    ) -> list[HybridResult]:
        """Version asincrona de :meth:`retrieve` (Spec ruscadb-async-io).

        Ejecuta retrieval denso + disperso en un hilo del executor para no
        bloquear el event loop del orchestrator (el C-ABI de RuscaDB es
        sincrono y single-writer).

        Args:
            query: Consulta del usuario.
            top_k: Maximo de resultados fusionados a devolver.
            rerank: Reordena con MaxSim de ColBERT (ver :meth:`retrieve`).

        Returns:
            Lista de HybridResult ordenada por score descendente.

        Raises:
            ValueError: Si top_k no es positivo o la query es vacia.
        """
        import asyncio

        return await asyncio.to_thread(self.retrieve, query, top_k, rerank)

    def _dense_retrieve(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """Ejecuta la busqueda vectorial densa.

        Args:
            query: Consulta del usuario.
            top_k: Maximo de resultados.

        Returns:
            Resultados del vector store con 'id', 'score' y 'metadata'.
        """
        query_vector = self._embed_fn(query)
        return self._vector_store.search(
            self._collection, query_vector, top_k=top_k
        )

    def _sparse_retrieve(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """Ejecuta la busqueda dispersa BM25 (FTS5 o RuscaDB MATCH).

        Si el vector_store expone full_text_search (RuscaDB), se usa MATCH (BM25)
        nativo de RuscaDB; si no, se usa el fts_search inyectado.
        """
        vs = getattr(self, "_vector_store", None)
        if vs is not None and hasattr(vs, "full_text_search"):
            try:
                return vs.full_text_search(self._collection, query, top_k=top_k)
            except Exception as exc:  # noqa: BLE001 - fallback explicito y visible
                logger.warning(
                    "full_text_search de '%s' fallo (%s); fallback a FTS5",
                    type(vs).__name__,
                    exc,
                )
        return self._fts_search.search(query, top_k=top_k)

    @staticmethod
    def _fuse(
        dense: list[dict[str, Any]],
        sparse: list[dict[str, Any]],
    ) -> list[HybridResult]:
        """Fusiona rankings denso y disperso mediante Reciprocal Rank Fusion.

        RRF asigna a cada documento 1/(k + rank) por cada lista en la que
        aparece, sumando las contribuciones. Un documento presente en ambos
        rankings puntua mas que uno presente solo en uno (complementariedad).

        Args:
            dense: Resultados densos ordenados por relevancia.
            sparse: Resultados dispersos ordenados por relevancia.

        Returns:
            Lista de HybridResult con score RRF acumulado.
        """
        acc: dict[str, HybridResult] = {}
        for rank, item in enumerate(dense, start=1):
            doc_id = str(item.get("id", ""))
            if not doc_id:
                continue
            acc[doc_id] = HybridResult(
                doc_id=doc_id,
                score=1.0 / (_RRF_K + rank),
                dense_rank=rank,
                metadata=item.get("metadata", {}) or {},
            )
        for rank, item in enumerate(sparse, start=1):
            doc_id = str(item.get("id", ""))
            if not doc_id:
                continue
            if doc_id in acc:
                prev = acc[doc_id]
                acc[doc_id] = HybridResult(
                    doc_id=doc_id,
                    score=prev.score + 1.0 / (_RRF_K + rank),
                    dense_rank=prev.dense_rank,
                    sparse_rank=rank,
                    metadata=prev.metadata or item.get("metadata", {}) or {},
                )
            else:
                acc[doc_id] = HybridResult(
                    doc_id=doc_id,
                    score=1.0 / (_RRF_K + rank),
                    sparse_rank=rank,
                    metadata=item.get("metadata", {}) or {},
                )
        return list(acc.values())


# Re-export de pesos para consumidores que quieran un score ponderado
# (dense/sparse normalizados a [0,1] antes de combinar).
DENSE_WEIGHT = _DENSE_WEIGHT
SPARSE_WEIGHT = _SPARSE_WEIGHT