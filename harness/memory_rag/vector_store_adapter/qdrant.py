"""Adaptador Qdrant para el paquete ``vector_store_adapter``.

Extraido mecanicamente de ``vector_store_adapter.py`` (regla AGR < 500
lineas). Contiene ``QdrantAdapter``, la implementacion de alto
rendimiento para produccion que envuelve qdrant_client.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from .base import VectorStoreAdapter
from .models import SearchResult

logger = logging.getLogger("harness.memory_rag.vector_store_adapter")


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
