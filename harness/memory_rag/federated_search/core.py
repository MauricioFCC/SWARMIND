"""FederatedVectorSearch â€” nÃºcleo del buscador federado (extraccion mecanica).

Clase publica FederatedVectorSearch: inicializacion de backends,
deteccion de colapso single-harness y creacion de backends por defecto.
La busqueda y el re-ranking se heredan de mixins en submÃ³dulos contiguos.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from harness.memory_rag.vector_store_adapter import (
    VectorStoreAdapter,
    create_vector_store,
)
from harness.orchestrator.performance_cache import PerformanceCache

from .constants import (
    DEFAULT_CACHE_MAX_SIZE,
    DEFAULT_CACHE_TTL_SEC,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_MMR_LAMBDA,
)
from .rerank import _RerankMixin
from .search import _SearchMixin

logger = logging.getLogger(__name__)

class FederatedVectorSearch(_SearchMixin, _RerankMixin):
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
        backends: dict[str, VectorStoreAdapter] | None = None,
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
        self._backends: dict[str, VectorStoreAdapter] = {}
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
        self._stats: dict[str, Any] = {
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

    def _detect_collapse(self) -> None:
        """Detecta si el runtime actual es single-harness para colapsar backends.

        Si solo hay un runtime activo (single-harness), colapsa a 1 backend
        (LanceDB) para reducir overhead innecesario en busquedas vectoriales.
        En multi-harness se usan los 3 backends para federacion completa.
        """
        try:
            from harness.orchestrator.multi_harness.runtime_detector import detect_runtime
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
        self, backends: dict[str, VectorStoreAdapter] | None
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
            configs: list[tuple[str, str, dict[str, Any]]] = [
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
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "No se pudo crear backend '%s' (%s): %s. "
                    "WHY: dependencia no instalada o fallo de conexion. "
                    "WHERE: FederatedVectorSearch._create_default_backends. "
                    "El sistema seguira funcionando con los backends disponibles.",
                    name, backend_type, exc,
                )
