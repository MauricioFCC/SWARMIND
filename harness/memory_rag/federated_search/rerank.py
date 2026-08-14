"""Re-ranking MMR y normalizacion de scores (extraccion mecanica).

Mixin privado con normalizacion min-max por backend, Maximum
Marginal Relevance, similitud entre items y generacion de cache key.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .models import FederatedResult


class _RerankMixin:
    """Re-ranking MMR y normalizacion para FederatedVectorSearch."""
    @staticmethod
    def _normalize_scores(results: list[FederatedResult]) -> list[FederatedResult]:
        """Normaliza puntuaciones con min-max scaling independiente por backend.

        Cada backend puede tener escalas de puntuacion diferentes:
        - LanceDB: distancia L2 (0 = identico, valores positivos).
        - Chroma: score = 1 - distancia (0 a 1).
        - Qdrant: cosine similarity (-1 a 1).

        El scaling transforma cada grupo al rango [0, 1] donde 1 es el mejor.

        Args:
            results: Lista de FederatedResult sin normalizar.

        Returns:
            Nueva lista con scores normalizados en [0, 1].
        """
        if not results:
            return results

        # Agrupar scores por backend
        backend_scores: dict[str, list[tuple[int, float]]] = {}
        for idx, r in enumerate(results):
            backend_scores.setdefault(r.backend, []).append((idx, r.score))

        # Crear copia para no mutar originales
        normalized: list[FederatedResult] = []
        for r in results:
            normalized.append(
                FederatedResult(
                    id=r.id,
                    score=r.score,
                    payload=dict(r.payload),
                    backend=r.backend,
                    vector=r.vector[:] if r.vector is not None else None,
                )
            )

        # Aplicar min-max scaling por backend
        for scores in backend_scores.values():
            values = [s[1] for s in scores]
            if not values:
                continue
            min_val = min(values)
            max_val = max(values)
            range_val = max_val - min_val

            if range_val < 1e-12:
                # Todos iguales -> asignar 1.0
                for idx, _ in scores:
                    normalized[idx].score = 1.0
            else:
                for idx, val in scores:
                    normalized[idx].score = (val - min_val) / range_val

        return normalized

    @staticmethod
    def _mmr_rerank(
        results: list[FederatedResult],
        query_vector: list[float],
        lambda_param: float,
        top_k: int,
    ) -> list[FederatedResult]:
        """Re-ranking por Maximum Marginal Relevance (MMR).

        Balancea relevancia contra diversidad seleccionando iterativamente
        el elemento que maximiza::

            MMR = lambda * sim(d, q) - (1 - lambda) * max_{j in S} sim(d, d_j)

        donde ``sim(d, q)`` es la relevancia al query y ``sim(d, d_j)``
        es la similitud entre items (para evitar redundancia).

        La similitud entre items se calcula como cosine similarity de sus
        vectores originales si estan disponibles. Como fallback, se usa
        ``1 - abs(score_i - score_j)``.

        Args:
            results: Lista de candidatos con scores normalizados.
            query_vector: Vector de consulta original.
            lambda_param: Factor de balance (0 = solo diversidad, 1 = solo relevancia).
            top_k: Numero de items a seleccionar.

        Returns:
            Lista de hasta ``top_k`` items re-rankeados.
        """
        if not results or top_k <= 0:
            return []

        # No hacer MMR si lambda es 1.0 (solo relevancia)
        if lambda_param >= 1.0:
            return sorted(results, key=lambda r: r.score, reverse=True)[:top_k]

        # Si solo hay 1 resultado o top_k=1, retornar el mejor
        if len(results) <= 1 or top_k <= 1:
            return [max(results, key=lambda r: r.score)]

        # Convertir query_vector a numpy
        query_np = np.array(query_vector, dtype=np.float64)
        query_norm = query_np / (np.linalg.norm(query_np) + 1e-12)

        # Preparar vectores de items (con fallback)
        item_vectors: list[np.ndarray | None] = []
        for r in results:
            if r.vector is not None and len(r.vector) > 0:
                v = np.array(r.vector, dtype=np.float64)
                norm = np.linalg.norm(v)
                item_vectors.append(v / (norm + 1e-12) if norm > 0 else None)
            else:
                item_vectors.append(None)

        # Pre-calcular similitud al query (relevancia)
        relevance: list[float] = []
        for r, vec in zip(results, item_vectors):
            if vec is not None:
                rel = float(np.dot(vec, query_norm))
            else:
                # Fallback: usar score normalizado como relevancia
                rel = r.score
            relevance.append(rel)

        # MMR greedy selection
        selected_indices: list[int] = []
        candidate_indices = set(range(len(results)))

        # Paso 1: seleccionar el item con mayor relevancia
        first_idx = max(candidate_indices, key=lambda i: relevance[i])
        selected_indices.append(first_idx)
        candidate_indices.remove(first_idx)

        # Pasos siguientes: MMR iterativo
        while len(selected_indices) < top_k and candidate_indices:
            best_idx = -1
            best_mmr = -float("inf")

            for i in candidate_indices:
                # Relevancia
                mmr_score = lambda_param * relevance[i]

                # Penalizacion por diversidad: max similitud con seleccionados
                max_sim = -1.0
                for j in selected_indices:
                    sim_ij = _RerankMixin._item_similarity(
                        i, j, results, item_vectors,
                    )
                    max_sim = max(max_sim, sim_ij)

                mmr_score -= (1.0 - lambda_param) * max_sim

                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_idx = i

            if best_idx < 0:
                break

            selected_indices.append(best_idx)
            candidate_indices.remove(best_idx)

        return [results[i] for i in selected_indices]

    @staticmethod
    def _item_similarity(
        i: int,
        j: int,
        results: list[FederatedResult],
        item_vectors: list[np.ndarray | None],
    ) -> float:
        """Calcula similitud entre dos items.

        Usa cosine similarity de vectores si disponibles, sino
        estima por diferencia de scores.

        Args:
            i: Indice del primer item.
            j: Indice del segundo item.
            results: Lista completa de resultados.
            item_vectors: Lista de vectores numpy normalizados o None.

        Returns:
            Similitud en [0, 1] donde 1 = identicos.
        """
        vec_i = item_vectors[i]
        vec_j = item_vectors[j]

        if vec_i is not None and vec_j is not None:
            # Cosine similarity
            sim = float(np.dot(vec_i, vec_j))
            return max(0.0, min(1.0, sim))

        # Fallback: basado en score (si scores son cercanos, son similares)
        score_diff = abs(results[i].score - results[j].score)
        return max(0.0, 1.0 - score_diff)

    @staticmethod
    def _make_cache_key(
        vector: list[float],
        collection: str,
        top_k: int,
        filters: dict[str, Any] | None,
        use_mmr: bool,
        mmr_lambda: float,
    ) -> str:
        """Genera clave de cache deterministica a partir de los parametros.

        Args:
            vector: Vector de consulta.
            collection: Nombre de coleccion.
            top_k: Numero de resultados.
            filters: Filtros de metadatos.
            use_mmr: Si se aplico MMR.
            mmr_lambda: Factor lambda de MMR.

        Returns:
            Clave hash unica para el cache.
        """
        import hashlib
        # Reducir vector a precision limitada para evitar variaciones de floating point
        vector_bytes = ",".join(f"{v:.6f}" for v in vector[:16]).encode("utf-8")
        filter_bytes = str(sorted((filters or {}).items())).encode("utf-8")

        raw = (
            vector_bytes
            + collection.encode("utf-8")
            + str(top_k).encode("utf-8")
            + filter_bytes
            + str(use_mmr).encode("utf-8")
            + f"{mmr_lambda:.4f}".encode()
        )
        return hashlib.sha256(raw).hexdigest()
