"""Adaptador abstracto base para el paquete ``vector_store_adapter``.

Extraido mecanicamente de ``vector_store_adapter.py`` (regla AGR < 500
lineas). Contiene la clase abstracta ``VectorStoreAdapter`` que define
el contrato que todos los adaptadores concretos deben cumplir.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import SearchResult

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
