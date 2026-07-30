"""
VectorStoreAdapter — Abstraction for multiple vector databases.

Soporta: LanceDB (actual), Chroma (serverless), Qdrant (production).
Patron: Strategy/Adapter similar a SQLAlchemy para vectores.
"""
from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """Resultado de una busqueda vectorial.

    Attributes:
        id: Identificador unico del resultado.
        score: Puntaje de similitud (0-1, mas alto es mejor).
        payload: Metadatos asociados al vector.
        vector: Vector original (opcional, util para debugging).
    """
    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)
    vector: list[float] | None = None


# ---------------------------------------------------------------------------
# Abstract adapter
# ---------------------------------------------------------------------------


class VectorStoreAdapter(ABC):
    """Interfaz abstracta para bases de datos vectoriales.

    Define el contrato que todos los adaptadores deben cumplir.
    Las implementaciones concretas envuelven clientes nativos de
    LanceDB, Chroma, Qdrant, etc.
    """

    @abstractmethod
    def create_collection(self, name: str, dimension: int = 384) -> None:
        """Crea una coleccion (tabla) en el vector store.

        Args:
            name: Nombre de la coleccion.
            dimension: Dimensionalidad del embedding (default: 384).

        Raises:
            RuntimeError: Si la coleccion no puede crearse.
        """

    @abstractmethod
    def add(
        self,
        collection: str,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        ids: list[str] | None = None,
    ) -> list[str]:
        """Agrega vectores con sus metadatos a una coleccion.

        Args:
            collection: Nombre de la coleccion destino.
            vectors: Lista de vectores (cada uno es List[float]).
            payloads: Lista de diccionarios con metadatos, uno por vector.
            ids: IDs opcionales. Si no se proveen, se generan automaticamente.

        Returns:
            Lista de IDs asignados a los registros insertados.

        Raises:
            RuntimeError: Si la coleccion no existe o falla la insercion.
        """

    @abstractmethod
    def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Busqueda por similitud vectorial con filtros opcionales.

        Args:
            collection: Nombre de la coleccion.
            vector: Vector de consulta.
            top_k: Numero maximo de resultados (default: 5).
            filters: Filtros de metadatos (campo -> valor).

        Returns:
            Lista de SearchResult ordenados por score descendente.

        Raises:
            RuntimeError: Si la coleccion no existe.
        """

    @abstractmethod
    def delete(self, collection: str, ids: list[str]) -> None:
        """Elimina registros por sus IDs.

        Args:
            collection: Nombre de la coleccion.
            ids: Lista de IDs a eliminar.

        Raises:
            RuntimeError: Si la coleccion no existe o falla la eliminacion.
        """

    @abstractmethod
    def list_collections(self) -> list[str]:
        """Lista todas las colecciones disponibles.

        Returns:
            Lista de nombres de coleccion.
        """


# ---------------------------------------------------------------------------
# LanceDB adapter
# ---------------------------------------------------------------------------


class LanceDBAdapter(VectorStoreAdapter):
    """Adaptador para LanceDB (actual en produccion).

    Envuelve el cliente nativo de LanceDB conectando a una base
    local en disco. Es la implementacion por defecto del sistema.

    Args:
        db_path: Ruta al directorio de la base LanceDB.
    """

    def __init__(self, db_path: str = "data/lancedb") -> None:
        """Inicializa el adaptador conectando a LanceDB.

        Args:
            db_path: Ruta donde LanceDB persiste los datos.

        Raises:
            RuntimeError: Si LanceDB no esta instalado.
        """
        self._db_path = db_path
        self._db = None
        self._init()

    def _init(self) -> None:
        """Importa lancedb y establece la conexion."""
        try:
            import lancedb  # type: ignore[import-untyped]
            self._db = lancedb.connect(self._db_path)
            logger.info("LanceDBAdapter conectado a %s", self._db_path)
        except ImportError as exc:
            raise RuntimeError(
                "LanceDB no esta instalado. Ejecuta: pip install lancedb"
            ) from exc

    def create_collection(self, name: str, dimension: int = 384) -> None:
        """Crea una tabla LanceDB con un vector de ejemplo para definir el schema.

        Args:
            name: Nombre de la tabla/coleccion.
            dimension: Dimension del embedding.

        Raises:
            RuntimeError: Si la tabla no puede crearse.
        """
        try:
            self._db.create_table(
                name,
                [{"vector": [0.0] * dimension}],
                mode="overwrite",
            )
            logger.debug("LanceDBAdapter: coleccion '%s' creada (dim=%d)", name, dimension)
        except Exception as exc:
            raise RuntimeError(
                f"LanceDBAdapter: no se pudo crear coleccion '{name}': {exc}"
            ) from exc

    def add(
        self,
        collection: str,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        ids: list[str] | None = None,
    ) -> list[str]:
        """Agrega registros a una tabla LanceDB.

        Args:
            collection: Nombre de la tabla.
            vectors: Vectores a insertar.
            payloads: Metadatos asociados.
            ids: IDs opcionales. Si no se proveen, se usa hash del payload.

        Returns:
            IDs asignados a los registros insertados.
        """

        data: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat()
        for i, (vec, payload) in enumerate(zip(vectors, payloads)):
            record_id = (
                ids[i]
                if ids and i < len(ids)
                else str(hash(str(payload) + now))
            )
            row: dict[str, Any] = {"id": record_id, "vector": vec, "created_at": now}
            row.update(payload)
            data.append(row)

        tbl = self._db.open_table(collection)
        tbl.add(data)
        logger.debug("LanceDBAdapter: %d registros agregados a '%s'", len(data), collection)
        return [d["id"] for d in data]

    def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Busqueda vectorial en tabla LanceDB con post-filtro opcional.

        Args:
            collection: Nombre de la tabla.
            vector: Vector de consulta.
            top_k: Maximo de resultados.
            filters: Filtros de metadatos (post-filtrado).

        Returns:
            Lista de SearchResult ordenados por distancia ascendente.
        """
        tbl = self._db.open_table(collection)
        # LanceDB devuelve los mas cercanos primero (menor distancia)
        results = tbl.search(vector).limit(top_k).to_list()

        # Post-filtro por metadatos
        if filters:
            filtered: list[dict[str, Any]] = []
            for r in results:
                match = all(
                    r.get(k) == v or r.get("payload", {}).get(k) == v
                    for k, v in filters.items()
                )
                if match:
                    filtered.append(r)
            results = filtered

        out: list[SearchResult] = []
        for r in results:
            payload = {k: v for k, v in r.items() if k not in ("id", "vector", "_distance")}
            out.append(
                SearchResult(
                    id=r.get("id", ""),
                    score=float(r.get("_distance", 0.0)),
                    payload=payload,
                    vector=r.get("vector"),
                )
            )
        return out

    def delete(self, collection: str, ids: list[str]) -> None:
        """Elimina registros por ID en una tabla LanceDB.

        Args:
            collection: Nombre de la tabla.
            ids: IDs a eliminar.

        Raises:
            RuntimeError: Si falla la eliminacion.
        """
        tbl = self._db.open_table(collection)
        for rid in ids:
            try:
                tbl.delete(f"id = '{rid}'")
            except Exception as exc:
                raise RuntimeError(
                    f"LanceDBAdapter: fallo al eliminar id '{rid}' "
                    f"en '{collection}': {exc}"
                ) from exc
        logger.debug("LanceDBAdapter: %d registros eliminados de '%s'", len(ids), collection)

    def list_collections(self) -> list[str]:
        """Lista las tablas disponibles en la base LanceDB.

        Returns:
            Lista de nombres de tabla.
        """
        return self._db.table_names()


# ---------------------------------------------------------------------------
# Chroma adapter
# ---------------------------------------------------------------------------


class ChromaAdapter(VectorStoreAdapter):
    """Adaptador para Chroma (serverless, alternativa ligera).

    Envuelve chromadb.PersistentClient para operaciones locales.
    Ideal para prototipado, desarrollo y entornos serverless.

    Args:
        db_path: Ruta al directorio de persistencia de Chroma.
    """

    def __init__(self, db_path: str = "data/chromadb") -> None:
        """Inicializa el adaptador conectando a Chroma Persistente.

        Args:
            db_path: Ruta donde Chroma persiste los datos.

        Raises:
            RuntimeError: Si chromadb no esta instalado.
        """
        self._db_path = db_path
        self._client = None
        try:
            import chromadb  # type: ignore[import-untyped]
            self._client = chromadb.PersistentClient(path=db_path)
            logger.info("ChromaAdapter conectado a %s", db_path)
        except ImportError as exc:
            raise RuntimeError(
                "chromadb no esta instalado. Ejecuta: pip install chromadb"
            ) from exc

    def create_collection(self, name: str, dimension: int = 384) -> None:
        """Crea una coleccion Chroma (si no existe, la crea).

        Args:
            name: Nombre de la coleccion.
            dimension: Dimension del embedding (ignorado en Chroma, se infiere).

        Raises:
            RuntimeError: Si la coleccion no puede crearse.
        """
        try:
            self._client.create_collection(name)
            logger.debug("ChromaAdapter: coleccion '%s' creada", name)
        except Exception as exc:
            raise RuntimeError(
                f"ChromaAdapter: no se pudo crear coleccion '{name}': {exc}"
            ) from exc

    def add(
        self,
        collection: str,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        ids: list[str] | None = None,
    ) -> list[str]:
        """Agrega vectores con metadatos a una coleccion Chroma.

        Args:
            collection: Nombre de la coleccion.
            vectors: Vectores a insertar.
            payloads: Metadatos (chroma los llama metadatas).
            ids: IDs opcionales; si no se proveen se generan como str(i).

        Returns:
            Lista de IDs asignados.
        """
        col = self._client.get_collection(collection)
        resolved_ids = ids or [str(i) for i in range(len(vectors))]
        col.add(embeddings=vectors, metadatas=payloads, ids=resolved_ids)
        logger.debug("ChromaAdapter: %d registros agregados a '%s'", len(vectors), collection)
        return resolved_ids

    def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Busqueda vectorial en Chroma con filtro opcional (where).

        Args:
            collection: Nombre de la coleccion.
            vector: Vector de consulta.
            top_k: Maximo de resultados.
            filters: Filtros where de Chroma.

        Returns:
            Lista de SearchResult.
        """
        col = self._client.get_collection(collection)
        where = filters or {}
        try:
            results = col.query(
                query_embeddings=[vector],
                n_results=top_k,
                where=where,
            )
        except Exception as exc:
            raise RuntimeError(
                f"ChromaAdapter: fallo busqueda en '{collection}': {exc}"
            ) from exc

        out: list[SearchResult] = []
        ids_list = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        for i in range(len(ids_list)):
            # Chroma devuelve distancia L2; convertir a score (1 - distancia)
            distance = float(distances[i]) if i < len(distances) else 0.0
            score = 1.0 - distance
            payload = metadatas[i] if i < len(metadatas) else {}
            out.append(
                SearchResult(
                    id=ids_list[i],
                    score=max(0.0, score),
                    payload=payload if isinstance(payload, dict) else {},
                )
            )
        return out

    def delete(self, collection: str, ids: list[str]) -> None:
        """Elimina registros por ID en Chroma.

        Args:
            collection: Nombre de la coleccion.
            ids: IDs a eliminar.
        """
        col = self._client.get_collection(collection)
        col.delete(ids=ids)
        logger.debug("ChromaAdapter: %d registros eliminados de '%s'", len(ids), collection)

    def list_collections(self) -> list[str]:
        """Lista las colecciones disponibles en Chroma.

        Returns:
            Lista de nombres de coleccion.
        """
        return [c.name for c in self._client.list_collections()]


# ---------------------------------------------------------------------------
# Qdrant adapter
# ---------------------------------------------------------------------------


class QdrantAdapter(VectorStoreAdapter):
    """Adaptador para Qdrant (produccion, alto rendimiento).

    Envuelve qdrant_client.QdrantClient para operaciones de
    colecciones, puntos y busqueda. Soporta filtros nativos.

    Args:
        host: Host del servidor Qdrant (default: localhost).
        port: Puerto gRPC (default: 6334).
        prefer_grpc: Usar canal gRPC (default: True).
        api_key: API key opcional para Qdrant Cloud.
        location: Ubicacion alternativa (local path o :memory:).
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6334,
        prefer_grpc: bool = True,
        api_key: str | None = None,
        location: str | None = None,
    ) -> None:
        """Inicializa el adaptador conectando a Qdrant.

        Args:
            host: Host del servidor Qdrant.
            port: Puerto del servidor.
            prefer_grpc: Usar canal gRPC para comunicacion.
            api_key: API key para autenticacion.
            location: Ruta local o ':memory:' para modo embedido.

        Raises:
            RuntimeError: Si qdrant-client no esta instalado.
        """
        self._host = host
        self._port = port
        self._prefer_grpc = prefer_grpc
        self._api_key = api_key
        self._location = location
        self._client = None
        self._init()

    def _init(self) -> None:
        """Importa qdrant_client y establece la conexion."""
        try:
            from qdrant_client import QdrantClient  # type: ignore[import-untyped]

            if self._location:
                self._client = QdrantClient(location=self._location)
            else:
                self._client = QdrantClient(
                    host=self._host,
                    port=self._port,
                    prefer_grpc=self._prefer_grpc,
                    api_key=self._api_key,
                )
            logger.info(
                "QdrantAdapter conectado a %s:%s", self._host, self._port
            )
        except ImportError as exc:
            raise RuntimeError(
                "qdrant-client no esta instalado. Ejecuta: pip install qdrant-client"
            ) from exc

    @staticmethod
    def _models():
        """Importa y retorna el modulo qdrant_client.http.models.

        Returns:
            Modulo models de qdrant_client.http.

        Raises:
            RuntimeError: Si qdrant-client no esta instalado.
        """
        try:
            from qdrant_client.http import models  # type: ignore[import-untyped]
            return models
        except ImportError as exc:
            raise RuntimeError(
                "qdrant-client no esta instalado. Ejecuta: pip install qdrant-client"
            ) from exc

    def create_collection(self, name: str, dimension: int = 384) -> None:
        """Crea una coleccion Qdrant con configuracion de vectores.

        Args:
            name: Nombre de la coleccion.
            dimension: Dimension del embedding.

        Raises:
            RuntimeError: Si la coleccion no puede crearse.
        """
        models = self._models()

        try:
            self._client.recreate_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.debug(
                "QdrantAdapter: coleccion '%s' creada (dim=%d)", name, dimension
            )
        except Exception as exc:
            raise RuntimeError(
                f"QdrantAdapter: no se pudo crear coleccion '{name}': {exc}"
            ) from exc

    def add(
        self,
        collection: str,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        ids: list[str] | None = None,
    ) -> list[str]:
        """Agrega puntos (vectores + payload) a una coleccion Qdrant.

        Args:
            collection: Nombre de la coleccion.
            vectors: Vectores a insertar.
            payloads: Payload (metadatos) asociados.
            ids: IDs opcionales; si no se proveen se generan UUIDs.

        Returns:
            Lista de IDs asignados.
        """
        models = self._models()

        resolved_ids = ids or [str(uuid.uuid4()) for _ in range(len(vectors))]
        points: list[models.PointStruct] = []  # type: ignore[name-defined]
        for rid, vec, payload in zip(resolved_ids, vectors, payloads):
            points.append(
                models.PointStruct(
                    id=rid,
                    vector=vec,
                    payload=payload,
                )
            )
        self._client.upsert(
            collection_name=collection,
            points=points,
        )
        logger.debug("QdrantAdapter: %d puntos upserted en '%s'", len(points), collection)
        return resolved_ids

    def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Busqueda vectorial en Qdrant con filtro nativo.

        Args:
            collection: Nombre de la coleccion.
            vector: Vector de consulta.
            top_k: Maximo de resultados.
            filters: Filtros Qdrant-style (dict campo -> valor).

        Returns:
            Lista de SearchResult.
        """
        models = self._models()

        query_filter = None
        if filters:
            conditions = [
                models.FieldCondition(
                    key=k,
                    match=models.MatchValue(value=v),
                )
                for k, v in filters.items()
            ]
            query_filter = models.Filter(must=conditions)

        try:
            results = self._client.search(
                collection_name=collection,
                query_vector=vector,
                limit=top_k,
                query_filter=query_filter,
            )
        except Exception as exc:
            raise RuntimeError(
                f"QdrantAdapter: fallo busqueda en '{collection}': {exc}"
            ) from exc

        out: list[SearchResult] = []
        for scored_point in results:
            out.append(
                SearchResult(
                    id=str(scored_point.id),
                    score=float(scored_point.score),
                    payload=dict(scored_point.payload) if scored_point.payload else {},
                    vector=scored_point.vector,
                )
            )
        return out

    def delete(self, collection: str, ids: list[str]) -> None:
        """Elimina puntos por ID en Qdrant.

        Args:
            collection: Nombre de la coleccion.
            ids: IDs a eliminar (como string o integer).
        """
        self._client.delete(
            collection_name=collection,
            points_selector=ids,
        )
        logger.debug("QdrantAdapter: %d puntos eliminados de '%s'", len(ids), collection)

    def list_collections(self) -> list[str]:
        """Lista las colecciones disponibles en Qdrant.

        Returns:
            Lista de nombres de coleccion.
        """
        collections = self._client.get_collections()
        return [c.name for c in collections.collections]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_vector_store(backend: str = "lancedb", **kwargs: Any) -> VectorStoreAdapter:
    """Factory method para crear instancias de adaptadores vectoriales.

    Selecciona y configura el adaptador segun el backend solicitado.
    Sigue el patron Abstract Factory para centralizar la creacion.

    Args:
        backend: Nombre del backend ('lancedb', 'chroma', 'qdrant').
        **kwargs: Argumentos especificos del adaptador (ej: db_path, host, port).

    Returns:
        Instancia de VectorStoreAdapter configurada.

    Raises:
        ValueError: Si el backend no es soportado.

    Examples:
        >>> store = create_vector_store("chroma", db_path="/tmp/chroma")
        >>> store = create_vector_store("qdrant", host="qdrant.example.com", port=6334)
    """
    adapters: dict[str, type] = {
        "lancedb": LanceDBAdapter,
        "chroma": ChromaAdapter,
        "qdrant": QdrantAdapter,
    }
    cls = adapters.get(backend)
    if not cls:
        raise ValueError(
            f"Backend desconocido: '{backend}'. "
            f"Opciones disponibles: {list(adapters.keys())}"
        )
    instance = cls(**kwargs)
    logger.info("VectorStoreAdapter creado: %s (backend=%s)", type(instance).__name__, backend)
    return instance
