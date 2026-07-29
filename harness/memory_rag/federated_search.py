"""FederatedVectorSearch — Busqueda vectorial federada multi-backend.

Realiza busqueda en paralelo sobre LanceDB, ChromaDB y Qdrant,
fusiona resultados con re-ranking por puntuacion y diversidad.

Basado en el patron de busqueda federada descrito en AI agents.txt.

Arquitectura:
- Cada backend se consulta en paralelo (ThreadPoolExecutor).
- Los resultados se normalizan (min-max scaling por backend).
- Se aplica re-ranking por Maximum Marginal Relevance (MMR).
- Se cachean resultados recientes via PerformanceCache.

Benefits:
- 3 backends simultaneos vs 1 antes.
- Re-ranking MMR: diversidad + relevancia.
- Cache de resultados con TTL configurable.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from harness.common import EMPTY_VECTOR, fallback_embedding
from harness.memory_rag.vector_store_adapter import (
    SearchResult,
    VectorStoreAdapter,
    create_vector_store,
)
from harness.orchestrator.performance_cache import PerformanceCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TOP_K_PER_BACKEND = 20  # recolectar mas de cada backend para fusion
DEFAULT_MMR_LAMBDA = 0.5        # balance relevancia (0) vs diversidad (1)
DEFAULT_CACHE_MAX_SIZE = 100
DEFAULT_CACHE_TTL_SEC = 300.0   # 5 minutos
DEFAULT_EMBEDDING_DIM = 384
_DEFAULT_BACKENDS = ("lancedb", "chroma", "qdrant")


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class FederatedResult:
    """Resultado federado de busqueda multi-backend.

    Attributes:
        id: Identificador unico del registro.
        score: Puntaje de similitud normalizado (0-1, mas alto es mejor).
        payload: Metadatos asociados al vector.
        backend: Nombre del backend origen (lancedb, chroma, qdrant).
        vector: Vector original (opcional, util para MMR).
    """
    id: str
    score: float
    payload: Dict[str, Any] = field(default_factory=dict)
    backend: str = ""
    vector: Optional[List[float]] = None


@dataclass
class FederatedStats:
    """Estadisticas de una busqueda federada.

    Attributes:
        total_requests: Total de busquedas realizadas.
        cache_hits: Veces que se sirvio desde cache.
        cache_misses: Veces que no habia cache.
        backends_available: Cuantos backends respondieron.
        backends_total: Cuantos backends estaban configurados.
        avg_latency_ms: Latencia promedio por busqueda.
    """
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    backends_available: int = 0
    backends_total: int = 0
    avg_latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# FederatedVectorSearch
# ---------------------------------------------------------------------------


class FederatedVectorSearch:
    """Busqueda vectorial federada multi-backend.

    Realiza busqueda en paralelo sobre LanceDB, ChromaDB y Qdrant,
    fusiona resultados con re-ranking por puntuacion y diversidad (MMR).

    Metodo principal::

        fvs = FederatedVectorSearch()
        resultados = fvs.search(
            vector=[0.1, 0.2, ...],
            collection="procedural_skills",
            top_k=5,
        )

    Uso con backends personalizados::

        backends = {
            "lancedb": LanceDBAdapter(db_path="data/lancedb"),
            "qdrant": QdrantAdapter(host="localhost", port=6334),
        }
        fvs = FederatedVectorSearch(backends=backends)
    """

    def __init__(
        self,
        backends: Optional[Dict[str, VectorStoreAdapter]] = None,
        mmr_lambda: float = DEFAULT_MMR_LAMBDA,
        cache_max_size: int = DEFAULT_CACHE_MAX_SIZE,
        cache_ttl: float = DEFAULT_CACHE_TTL_SEC,
        embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    ) -> None:
        """Inicializa el buscador federado con los backends especificados.

        Args:
            backends: Dict nombre -> instancia VectorStoreAdapter.
                Si es None, se crean backends por defecto (LanceDB, Chroma, Qdrant)
                con configuracion local estandar.
            mmr_lambda: Factor lambda para MMR re-ranking.
                0.0 = solo relevancia (sin diversidad).
                1.0 = solo diversidad (sin relevancia).
                Default: 0.5 (balance).
            cache_max_size: Numero maximo de entradas en cache.
            cache_ttl: Tiempo de vida en segundos de entradas en cache.
            embedding_dim: Dimension de los vectores de embedding.

        Raises:
            ValueError: Si mmr_lambda no esta en [0.0, 1.0].
        """
        if not 0.0 <= mmr_lambda <= 1.0:
            raise ValueError(
                f"mmr_lambda debe estar entre 0.0 y 1.0, recibido: {mmr_lambda}"
            )

        self._mmr_lambda = mmr_lambda
        self._embedding_dim = embedding_dim

        # Detectar si colapsar a 1 backend en single-harness
        self._collapse_backends: bool = False
        self._detect_collapse()

        # Inicializar backends
        self._backends: Dict[str, VectorStoreAdapter] = {}
        self._init_backends(backends)

        # Cache de resultados recientes
        self._cache = PerformanceCache(
            max_size=cache_max_size,
            ttl=cache_ttl,
        )

        # Pool de threads para busqueda paralela (min 1, incluso sin backends)
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, len(self._backends)),
            thread_name_prefix="federated_search",
        )

        # Estadisticas acumuladas
        self._stats: Dict[str, Any] = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_latency_ms": 0.0,
            "backends_available": len(self._backends),
            "backends_total": len(self._backends),
            "mmr_lambda": mmr_lambda,
        }

        logger.info(
            "FederatedVectorSearch inicializado con %d backends: %s, "
            "mmr_lambda=%.2f, cache=%d/%ds",
            len(self._backends),
            list(self._backends.keys()),
            mmr_lambda,
            cache_max_size,
            cache_ttl,
        )

    # ------------------------------------------------------------------
    # Inicializacion de backends
    # ------------------------------------------------------------------

    def _detect_collapse(self) -> None:
        """Detecta si el runtime actual es single-harness para colapsar backends.

        Si solo hay un runtime activo (single-harness), colapsa a 1 backend
        (LanceDB) para reducir overhead innecesario en busquedas vectoriales.
        En multi-harness se usan los 3 backends para federacion completa.
        """
        try:
            from harness.orchestrator.multi_harness.runtime_detector import (
                detect_runtime,
            )
            runtime = detect_runtime()
            self._collapse_backends = runtime.detected
            if self._collapse_backends:
                logger.info(
                    "FederatedSearch: runtime '%s' detectado, "
                    "colapsando a 1 backend (single-harness)",
                    runtime.name,
                )
        except ImportError:
            self._collapse_backends = False

    @property
    def is_collapsed(self) -> bool:
        """Indica si la busqueda federada esta colapsada a 1 backend.

        Returns:
            True si solo se usa LanceDB (single-harness), False si
            se usan los 3 backends completos (multi-harness).
        """
        return self._collapse_backends

    def _init_backends(
        self, backends: Optional[Dict[str, VectorStoreAdapter]]
    ) -> None:
        """Inicializa los backends, creando los por defecto si es necesario.

        Args:
            backends: Dict nombre -> adaptador o None para usar defaults.
                Si se pasa un dict vacio explicito, se respeta (sin backends).
        """
        if backends is not None:
            if not backends:
                # Dict vacio explicito: respetar decision del usuario
                logger.info(
                    "No se configuraron backends (dict vacio explicito). "
                    "Las busquedas retornaran listas vacias hasta que se "
                    "agreguen backends. WHERE: FederatedVectorSearch._init_backends"
                )
                return

            # Validar que todos sean VectorStoreAdapter
            valid_count = 0
            for name, adapter in backends.items():
                if not isinstance(adapter, VectorStoreAdapter):
                    logger.warning(
                        "Backend '%s' no es VectorStoreAdapter, se omite. "
                        "Tipo recibido: %s. WHERE: FederatedVectorSearch._init_backends",
                        name, type(adapter).__name__,
                    )
                    continue
                self._backends[name] = adapter
                valid_count += 1

            if valid_count == 0:
                logger.warning(
                    "Ningun backend valido en la configuracion proporcionada. "
                    "WHERE: FederatedVectorSearch._init_backends. "
                    "Se crearan backends por defecto."
                )
                self._create_default_backends()
            return

        self._create_default_backends()

    def _create_default_backends(self) -> None:
        """Crea los backends por defecto (LanceDB, Chroma, Qdrant).

        Si estamos en un entorno single-harness (runtime detectado),
        colapsa a solo 1 backend (LanceDB) para reducir overhead.
        En multi-harness usa los 3 backends para federacion completa.

        Cada backend se crea con configuracion local estandar.
        Si un backend falla al crear, se omite con un warning.
        """
        if self._collapse_backends:
            configs: List[Tuple[str, str, Dict[str, Any]]] = [
                ("lancedb", "lancedb", {"db_path": "data/lancedb"}),
            ]
            logger.info(
                "FederatedSearch: colapsado a 1 backend (LanceDB) "
                "por single-harness runtime",
            )
        else:
            configs = [
                ("lancedb", "lancedb", {"db_path": "data/lancedb"}),
                ("chroma", "chroma", {"db_path": "data/chromadb"}),
                ("qdrant", "qdrant", {"location": ":memory:"}),
            ]
        for name, backend_type, kwargs in configs:
            try:
                adapter = create_vector_store(backend_type, **kwargs)
                self._backends[name] = adapter
                logger.debug(
                    "Backend por defecto creado: %s (%s)",
                    name, backend_type,
                )
            except Exception as exc:
                logger.warning(
                    "No se pudo crear backend '%s' (%s): %s. "
                    "WHY: dependencia no instalada o fallo de conexion. "
                    "WHERE: FederatedVectorSearch._create_default_backends. "
                    "El sistema seguira funcionando con los backends disponibles.",
                    name, backend_type, exc,
                )

    # ------------------------------------------------------------------
    # Metodo principal: busqueda federada
    # ------------------------------------------------------------------

    def search(
        self,
        vector: List[float],
        collection: str,
        top_k: int = 5,
        top_k_per_backend: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        use_mmr: bool = True,
        mmr_lambda: Optional[float] = None,
    ) -> List[FederatedResult]:
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
        cached: Optional[List[FederatedResult]] = self._cache.get(cache_key)
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

        raw_results: List[FederatedResult] = []
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
            except Exception as exc:
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

    # ------------------------------------------------------------------
    # Busqueda individual por backend
    # ------------------------------------------------------------------

    def _search_backend(
        self,
        backend_name: str,
        adapter: VectorStoreAdapter,
        vector: List[float],
        collection: str,
        top_k: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[FederatedResult]:
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
            results: List[SearchResult] = adapter.search(
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

        federated: List[FederatedResult] = []
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

    # ------------------------------------------------------------------
    # Normalizacion de scores (min-max scaling por backend)
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_scores(results: List[FederatedResult]) -> List[FederatedResult]:
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
        backend_scores: Dict[str, List[Tuple[int, float]]] = {}
        for idx, r in enumerate(results):
            backend_scores.setdefault(r.backend, []).append((idx, r.score))

        # Crear copia para no mutar originales
        normalized: List[FederatedResult] = []
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
        for backend, scores in backend_scores.items():
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

    # ------------------------------------------------------------------
    # Re-ranking MMR (Maximum Marginal Relevance)
    # ------------------------------------------------------------------

    @staticmethod
    def _mmr_rerank(
        results: List[FederatedResult],
        query_vector: List[float],
        lambda_param: float,
        top_k: int,
    ) -> List[FederatedResult]:
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
        item_vectors: List[Optional[np.ndarray]] = []
        for r in results:
            if r.vector is not None and len(r.vector) > 0:
                v = np.array(r.vector, dtype=np.float64)
                norm = np.linalg.norm(v)
                item_vectors.append(v / (norm + 1e-12) if norm > 0 else None)
            else:
                item_vectors.append(None)

        # Pre-calcular similitud al query (relevancia)
        relevance: List[float] = []
        for r, vec in zip(results, item_vectors):
            if vec is not None:
                rel = float(np.dot(vec, query_norm))
            else:
                # Fallback: usar score normalizado como relevancia
                rel = r.score
            relevance.append(rel)

        # MMR greedy selection
        selected_indices: List[int] = []
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
                    sim_ij = FederatedVectorSearch._item_similarity(
                        i, j, results, item_vectors,
                    )
                    if sim_ij > max_sim:
                        max_sim = sim_ij

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
        results: List[FederatedResult],
        item_vectors: List[Optional[np.ndarray]],
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

    # ------------------------------------------------------------------
    # Cache key
    # ------------------------------------------------------------------

    @staticmethod
    def _make_cache_key(
        vector: List[float],
        collection: str,
        top_k: int,
        filters: Optional[Dict[str, Any]],
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
            + f"{mmr_lambda:.4f}".encode("utf-8")
        )
        return hashlib.sha256(raw).hexdigest()

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def get_available_backends(self) -> List[str]:
        """Retorna los nombres de backends actualmente disponibles.

        Returns:
            Lista de strings con nombres de backend.
        """
        return list(self._backends.keys())

    def get_stats(self) -> Dict[str, Any]:
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

    def __enter__(self) -> FederatedVectorSearch:
        """Soporte para context manager (with statement)."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Cierra recursos al salir del context manager."""
        self.close()


# ---------------------------------------------------------------------------
# Funcion factory de alto nivel
# ---------------------------------------------------------------------------


def create_federated_search(
    backends: Optional[Dict[str, VectorStoreAdapter]] = None,
    mmr_lambda: float = DEFAULT_MMR_LAMBDA,
    cache_max_size: int = DEFAULT_CACHE_MAX_SIZE,
    cache_ttl: float = DEFAULT_CACHE_TTL_SEC,
) -> FederatedVectorSearch:
    """Crea un FederatedVectorSearch con configuracion simplificada.

    Args:
        backends: Dict nombre -> adaptador. Si None, usa defaults.
        mmr_lambda: Factor de balance MMR (0-1).
        cache_max_size: Tamaño maximo del cache.
        cache_ttl: TTL en segundos del cache.

    Returns:
        Instancia de FederatedVectorSearch lista para usar.

    Example:
        >>> fvs = create_federated_search()
        >>> resultados = fvs.search([0.1]*384, "skills", top_k=3)
    """
    return FederatedVectorSearch(
        backends=backends,
        mmr_lambda=mmr_lambda,
        cache_max_size=cache_max_size,
        cache_ttl=cache_ttl,
    )
