"""Adaptador Chroma para el paquete ``vector_store_adapter``.

Extraido mecanicamente de ``vector_store_adapter.py`` (regla AGR < 500
lineas). Contiene ``ChromaAdapter``, alternativa ligera serverless.
"""
from __future__ import annotations

import logging
from typing import Any

from .base import VectorStoreAdapter
from .models import SearchResult

logger = logging.getLogger("harness.memory_rag.vector_store_adapter")


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
