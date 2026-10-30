"""Puertos (interfaces) del dominio SWARMIND — Clean Architecture hexagonal.

Estos Protocolos definen los contratos que la capa de aplicacion consume.
La infraestructura (adaptadores) los implementa. Las dependencias apuntan
SIEMPRE hacia este modulo (Domain), nunca al reves.

Los puertos siguen el principio de segregacion de interfaces (ISP, SOLID):
un backend solo debe implementar el contrato que realmente ofrece. Un store
que no soporta busqueda full-text NO implementa :class:`TextSearchPort`, y
eso es valido; lo invalido es fingir el metodo.

Referencia: Clean Architecture (Martin 2017), Hexagonal (Cockburn).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VectorStorePort(Protocol):
    """Contrato minimo de un almacen vectorial (CRUD + busqueda densa/hibrida).

    Todo backend de memoria (RuscaDB, LanceDB, in-memory) debe cumplirlo.
    La busqueda lexical se declara aparte en :class:`TextSearchPort` porque
    no todos los motores la ofrecen.
    """

    def list_collections(self) -> list[str]: ...

    def create_collection(self, name: str, schema: Any = None) -> None: ...

    def insert(
        self,
        collection: str,
        vectors: Any,
        metadata: list[dict[str, Any]],
        **kwargs: Any,
    ) -> list[str]: ...

    def search(
        self, collection: str, query_vector: Any, top_k: int = 5, **kwargs: Any
    ) -> list[dict[str, Any]]: ...

    def hybrid_search(
        self,
        collection: str,
        query_vector: Any,
        query_text: str = "",
        top_k: int = 5,
        **kwargs: Any,
    ) -> list[dict[str, Any]]: ...

    def delete(self, collection: str, ids: list[str]) -> int: ...

    def delete_collection(self, name: str) -> None: ...

    def clear(self) -> None: ...

    def get_collection_stats(self, name: str) -> dict[str, Any]: ...

    def close(self) -> None: ...


@runtime_checkable
class TextSearchPort(Protocol):
    """Contrato opcional de busqueda lexical (BM25/FTS) sobre el mismo store."""

    def full_text_search(
        self, collection: str, query: str, top_k: int = 10
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class BinarySearchPort(Protocol):
    """Contrato opcional de KNN cuantizado (1 bit + rescore exacto)."""

    def search_binary(
        self,
        collection: str,
        query_vector: Any,
        top_k: int = 10,
        oversample: int = 3,
        **kwargs: Any,
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class EmbeddingPort(Protocol):
    """Contrato de un generador de embeddings."""

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class LLMPort(Protocol):
    """Contrato de un modelo de lenguaje."""

    def complete(self, prompt: str, **kwargs: Any) -> str: ...


@runtime_checkable
class MemoryPort(Protocol):
    """Contrato de memoria clave-valor persistente."""

    def get(self, key: str) -> Any: ...

    def set(self, key: str, value: Any) -> None: ...

    def delete(self, key: str) -> None: ...


@runtime_checkable
class EventBusPort(Protocol):
    """Contrato de bus de eventos pub/sub."""

    def publish(self, topic: str, payload: Any) -> None: ...

    def subscribe(self, topic: str, handler: Any) -> None: ...


__all__ = [
    "BinarySearchPort",
    "EmbeddingPort",
    "EventBusPort",
    "LLMPort",
    "MemoryPort",
    "TextSearchPort",
    "VectorStorePort",
]
