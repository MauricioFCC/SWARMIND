"""GraphRAG de doble nivel sobre el grafo y FTS de RuscaDB.

Frontera: **LightRAG** (arXiv:2410.05779) y **GraphRAG** (arXiv:2404.16130)
muestran que combinar recuperacion local (texto/entidades) con expansion por
grafo mejora la coherencia de las respuestas frente a RAG plano. Este modulo
implementa el patron **dual-level** aprovechando dos capacidades nativas de
RuscaDB:

- nivel local: ``MATCH`` (BM25) para sembrar entidades/documentos relevantes;
- nivel global: ``TRAVERSE edges DEPTH n`` para incorporar vecinos del grafo.

Los dos rankings se fusionan con Reciprocal Rank Fusion (Cormack et al., 2009),
evitando comparar escalas de score incompatibles.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger("harness.memory_rag.graph_rag_retriever")

#: Constante de suavizado RRF (estandar de la literatura).
_RRF_K = 60


class _GraphStore(Protocol):
    """Contrato minimo del store para GraphRAG (facilita el test con dobles)."""

    def full_text_search(
        self, collection: str, query: str, top_k: int = 10
    ) -> list[dict[str, Any]]: ...

    def graph_traverse(
        self, collection: str, depth: int = 2, start: str | None = None
    ) -> list[dict[str, Any]]: ...


class GraphRAGRetriever:
    """Recuperador de doble nivel (local BM25 + expansion por grafo)."""

    def __init__(
        self,
        store: _GraphStore,
        collection: str = "memory",
        depth: int = 2,
        seed_k: int = 8,
        rrf_k: int = _RRF_K,
    ) -> None:
        """Configura el recuperador.

        Args:
            store: Store compatible (RuscaDBStore o doble de test).
            collection: Coleccion objetivo.
            depth: Profundidad de expansion del grafo (>= 1).
            seed_k: Tamano del conjunto semilla (nivel local).
            rrf_k: Constante de suavizado RRF.
        """
        self._store = store
        self._collection = collection
        self._depth = max(1, int(depth))
        self._seed_k = max(1, int(seed_k))
        self._rrf_k = max(1, int(rrf_k))

    def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Recupera documentos fusionando nivel local y expansion de grafo.

        Args:
            query: Consulta en lenguaje natural.
            top_k: Numero maximo de resultados.

        Returns:
            Lista de ``{id, text, metadata, score, local_rank, graph_rank}``
            ordenada por score RRF descendente. Los documentos solo locales
            tienen ``graph_rank = 0`` y viceversa.
        """
        if not query.strip() or top_k <= 0:
            return []
        seeds = self._store.full_text_search(
            self._collection, query, top_k=self._seed_k
        )
        expanded = self._expand(seeds)
        return self._fuse(seeds, expanded)[:top_k]

    def _expand(self, seeds: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Expande el contexto con el nivel global del grafo.

        RuscaDB devuelve en ``TRAVERSE edges DEPTH n`` los nodos conectados por
        aristas del corpus (el motor no admite ``WHERE`` sobre ``TRAVERSE``);
        por eso el nivel global se calcula una vez y se deduplica por id.

        Args:
            seeds: Resultados del nivel local (no altera la expansion).

        Returns:
            Nodos del grafo, deduplicados por id.
        """
        try:
            reached = self._store.graph_traverse(self._collection, depth=self._depth)
        except Exception as exc:  # noqa: BLE001
            logger.debug("graph_traverse fallo: %s", exc)
            return []
        neighbors: dict[str, dict[str, Any]] = {}
        for item in reached:
            key = str(item.get("id") or "")
            if key and key not in neighbors:
                neighbors[key] = item
        return list(neighbors.values())

    def _fuse(
        self, local: list[dict[str, Any]], graph: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Fusiona los dos niveles con Reciprocal Rank Fusion.

        Args:
            local: Ranking del nivel local (BM25).
            graph: Ranking del nivel global (vecinos del grafo).

        Returns:
            Lista fusionada y deduplicada por id, ordenada por score.
        """
        fused: dict[str, dict[str, Any]] = {}
        for rank, item in enumerate(local, start=1):
            key = str(item.get("id") or "")
            if not key:
                continue
            entry = dict(item)
            entry["score"] = 1.0 / (self._rrf_k + rank)
            entry["local_rank"] = rank
            entry["graph_rank"] = 0
            fused[key] = entry
        for rank, item in enumerate(graph, start=1):
            key = str(item.get("id") or "")
            if not key:
                continue
            entry = fused.setdefault(key, dict(item))
            entry["score"] = entry.get("score", 0.0) + 1.0 / (self._rrf_k + rank)
            entry.setdefault("local_rank", 0)
            entry["graph_rank"] = rank
        return sorted(fused.values(), key=lambda item: item["score"], reverse=True)
