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

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from harness.memory_rag.fts_search import FTSSearch
from harness.memory_rag.lance_vector_store import LanceVectorStore

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
        vector_store: LanceVectorStore,
        fts_search: FTSSearch,
        embed_fn: Callable[[str], np.ndarray],
        collection: str = _DEFAULT_COLLECTION,
    ) -> None:
        self._vector_store = vector_store
        self._fts_search = fts_search
        self._embed_fn = embed_fn
        self._collection = collection

    def retrieve(self, query: str, top_k: int = 5) -> list[HybridResult]:
        """Recupera documentos fusionando rankings denso y disperso (RRF).

        Args:
            query: Consulta del usuario.
            top_k: Maximo de resultados fusionados a devolver.

        Returns:
            Lista de HybridResult ordenada por score RRF descendente.

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
        dense_results = self._dense_retrieve(query, top_k)
        sparse_results = self._sparse_retrieve(query, top_k)
        fused = self._fuse(dense_results, sparse_results)
        return sorted(fused, key=lambda item: item.score, reverse=True)[:top_k]

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
        """Ejecuta la busqueda dispersa BM25 (FTS5).

        Args:
            query: Consulta del usuario.
            top_k: Maximo de resultados.

        Returns:
            Resultados del FTS con 'id' y 'score'.
        """
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