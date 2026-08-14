"""Excepciones del paquete ``lance_vector_store``.

Extraido mecanicamente de ``lance_vector_store.py`` (regla AGR < 500 lineas).
Sin cambios de logica: mismas clases, mismos mensajes.
"""
from __future__ import annotations


class CollectionNotFoundError(Exception):
    """Raised when an operation targets a non-existent collection."""


class VectorStoreError(Exception):
    """Base exception for vector store operations."""
