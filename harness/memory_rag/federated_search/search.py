"""Busqueda federada paralela (extraccion mecanica).

Mixin privado con el metodo principal `search` (busqueda en paralelo,
normalizacion, MMR, cache) y la busqueda individual por backend.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import as_completed
from typing import Any, Self

from harness.memory_rag.vector_store_adapter import (
    SearchResult,
    VectorStoreAdapter,
)

from .constants import DEFAULT_TOP_K_PER_BACKEND
from .models import FederatedResult

logger = logging.getLogger(__name__)


class _SearchMixin:
    """Busqueda federada usada por FederatedVectorSearch."""
    def search(
        self,
        vector: list[float],
        collection: str,
        top_k: int = 5,
        top_k_per_backend: int | None = None,
        filters: dict[str, Any] | None = None,
        use_mmr: bool = True,
        mmr_lambda: float | None = None,
    ) -> list[FederatedResult]:
        """Busqueda vectorial federada con fusion y re-ranking.

        Dispara consultas en paralelo a todos los backends disponibles,
        normaliza puntuaciones, aplica MMR re-ranking y cachea resultados.

        Args:
            vector: Vector de consulta (lista de floats).
            collection: Nombre de la coleccion a consultar.
            top_k: Numero maximo de resultados finales (default: 5).
            top_k_per_backend: Resultados a solicitar a cada backend.
                Si es None, usa max(20, top_k * 2).
            filters: Filtros de metadatos (campo -> valor).
            use_mmr: Si True, aplica re-ranking MMR (default: True).
            mmr_lambda: Factor lambda para MMR. Sobreescribe el default
                de instancia si se provee.

        Returns:
            Lista de FederatedResult ordenados por score descendente
            (despues de MMR si aplica).

        Raises:
            ValueError: Si vector esta vacio o collection es invalida.
        """
        # Validaciones
        if not vector or len(vector) == 0:
            raise ValueError(
                "El vector de consulta no puede estar vacio. "
                "WHY: no se puede buscar sin representacion vectorial. "
                "WHERE: FederatedVectorSearch.search"
            )
        if not collection or not isinstance(collection, str):
            raise ValueError(
                f"collection debe ser un string no vacio, recibido: {collection}. "
                "WHERE: FederatedVectorSearch.search"
            )

        self._stats["total_requests"] += 1
        start_time = time.perf_counter()

        effective_top_k_per_backend = (
            top_k_per_backend if top_k_per_backend is not None
            else max(DEFAULT_TOP_K_PER_BACKEND, top_k * 2)
        )

        effective_mmr_lambda = (
            mmr_lambda if mmr_lambda is not None
            else self._mmr_lambda
        )

        # --- Cache lookup ---
        cache_key = self._make_cache_key(
            vector, collection, top_k, filters, use_mmr, effective_mmr_lambda,
        )
        cached: list[FederatedResult] | None = self._cache.get(cache_key)
        if cached is not None:
            self._stats["cache_hits"] += 1
            elapsed = (time.perf_counter() - start_time) * 1000
            self._stats["total_latency_ms"] += elapsed
            logger.debug(
                "FederatedSearch CACHE HIT (collection=%s, cache_key=%s, %.1fms)",
                collection, cache_key[:12], elapsed,
            )
            return cached

        self._stats["cache_misses"] += 1

        # --- Busqueda paralela ---
        if not self._backends:
            logger.warning(
                "No hay backends disponibles para la busqueda. "
                "WHERE: FederatedVectorSearch.search. "
                "Retornando lista vacia."
            )
            return []

        raw_results: list[FederatedResult] = []
        futures = {}

        for name, adapter in self._backends.items():
            future = self._executor.submit(
                self._search_backend,
                backend_name=name,
                adapter=adapter,
                vector=vector,
                collection=collection,
                top_k=effective_top_k_per_backend,
                filters=filters,
            )
            futures[future] = name

        for future in as_completed(futures):
            backend_name = futures[future]
            try:
                backend_results = future.result()
                raw_results.extend(backend_results)
                logger.debug(
                    "Backend '%s' retorno %d resultados",
                    backend_name, len(backend_results),
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Fallo busqueda en backend '%s': %s. "
                    "WHY: error interno del adaptador o conexion. "
                    "WHERE: FederatedVectorSearch.search (as_completed). "
                    "El resultado de este backend se omite.",
                    backend_name, exc,
                )

        if not raw_results:
            elapsed = (time.perf_counter() - start_time) * 1000
            self._stats["total_latency_ms"] += elapsed
            logger.warning(
                "Ningun backend retorno resultados (collection=%s). "
                "WHERE: FederatedVectorSearch.search",
                collection,
            )
            return []

        # --- Normalizacion de scores ---
        normalized = self._normalize_scores(raw_results)

        # --- Re-ranking MMR ---
        if use_mmr:
            final_results = self._mmr_rerank(
                results=normalized,
                query_vector=vector,
                lambda_param=effective_mmr_lambda,
                top_k=top_k,
            )
        else:
            # Sin MMR: ordenar por score descendente y truncar
            sorted_results = sorted(
                normalized, key=lambda r: r.score, reverse=True
            )
            final_results = sorted_results[:top_k]

        # --- Cachear resultados ---
        self._cache.set(cache_key, final_results)

        elapsed = (time.perf_counter() - start_time) * 1000
        self._stats["total_latency_ms"] += elapsed

        logger.debug(
            "FederatedSearch completada: collection=%s, "
            "candidates=%d, final=%d, backends=%d, %.1fms",
            collection, len(raw_results), len(final_results),
            len(self._backends), elapsed,
        )

        return final_results

    def _search_backend(
        self,
        backend_name: str,
        adapter: VectorStoreAdapter,
        vector: list[float],
        collection: str,
        top_k: int,
        filters: dict[str, Any] | None,
    ) -> list[FederatedResult]:
        """Ejecuta busqueda en un backend y convierte resultados a FederatedResult.

        Args:
            backend_name: Nombre identificador del backend.
            adapter: Instancia del adaptador VectorStoreAdapter.
            vector: Vector de consulta.
            collection: Nombre de la coleccion.
            top_k: Maximo resultados a solicitar.
            filters: Filtros de metadatos.

        Returns:
            Lista de FederatedResult desde este backend.

        Raises:
            RuntimeError: Si falla la operacion en el backend.
        """
        try:
            results: list[SearchResult] = adapter.search(
                collection=collection,
                vector=vector,
                top_k=top_k,
                filters=filters,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Error en backend '{backend_name}' buscando en coleccion "
                f"'{collection}': {exc}. "
                f"WHY: fallo en VectorStoreAdapter.search. "
                f"WHERE: FederatedVectorSearch._search_backend"
            ) from exc

        federated: list[FederatedResult] = []
        for r in results:
            federated.append(
                FederatedResult(
                    id=r.id,
                    score=r.score,
                    payload=r.payload,
                    backend=backend_name,
                    vector=r.vector,
                )
            )
        return federated

    def get_backends(self) -> list[str]:
        """Retorna los nombres de los backends registrados.

        Returns:
            Lista de strings con nombres de backend.
        """
        return list(self._backends.keys())

    def get_available_backends(self) -> list[str]:
        """Retorna los nombres de los backends disponibles.

        Returns:
            Lista de strings con los nombres de backends activos.
        """
        return list(self._backends.keys())

    def get_stats(self) -> dict[str, Any]:
        """Retorna estadisticas acumuladas del buscador federado.

        Returns:
            Dict con metricas: total_requests, cache_hits, cache_misses,
            hit_rate, backends_available, backends_total, avg_latency_ms.
        """
        stats = dict(self._stats)
        total = stats.get("total_requests", 1)
        hits = stats.get("cache_hits", 0)
        stats["hit_rate"] = round(hits / max(total, 1), 3)
        total_ms = stats.get("total_latency_ms", 0.0)
        stats["avg_latency_ms"] = round(
            total_ms / max(total, 1), 1
        )
        return stats

    def close(self) -> None:
        """Libera recursos del pool de threads y backends.

        Debe llamarse al finalizar para limpiar correctamente.
        El objeto no debe reutilizarse despues de cerrarlo.
        """
        self._executor.shutdown(wait=True, cancel_futures=False)
        logger.info(
            "FederatedVectorSearch cerrado. "
            "Estadisticas finales: %s", self.get_stats(),
        )

    def __enter__(self) -> Self:
        """Soporte para context manager (with statement)."""
        return self

    def __exit__(self, *args: object) -> None:
        """Cierra recursos al salir del context manager."""
        self.close()
