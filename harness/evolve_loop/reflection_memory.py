"""Memoria episodica de reflexiones (Reflexion, arXiv:2303.11366).

Persiste reflexiones textuales en RuscaDB (FTS + vector) para que el harness
recursivo evite repetir errores ya analizados entre sesiones.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("harness.evolve_loop.reflection_memory")

_COLLECTION = "reflections"


class ReflectionMemory:
    """Memoria episodica de reflexiones sobre RuscaDB."""

    def __init__(self, store: Any, collection: str = _COLLECTION) -> None:
        """Configura la memoria.

        Args:
            store: Store compatible con VectorStorePort (RuscaDBStore).
            collection: Coleccion donde se persisten las reflexiones.
        """
        self._store = store
        self._collection = collection
        try:
            self._store.create_collection(collection)
        except Exception:  # noqa: BLE001, S110
            pass

    def store(self, reflection: str, context: dict[str, Any] | None = None) -> str:
        """Persiste una reflexion.

        Args:
            reflection: Texto de la reflexion.
            context: Metadata adicional (task_id, score, etc.).

        Returns:
            Id logico del registro (cadena vacia si fallo).
        """
        meta = {"reflection": reflection, "text": reflection}
        if context:
            meta.update(context)
        try:
            ids = self._store.insert(self._collection, [[0.0] * 8], [meta])
            return ids[0] if ids else ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("store reflection fallo: %s", exc)
            return ""

    def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Recupera reflexiones relevantes via FTS.

        Args:
            query: Consulta.
            top_k: Numero de resultados.

        Returns:
            Lista de registros con metadata.
        """
        try:
            return self._store.full_text_search(self._collection, query, top_k=top_k)
        except Exception:  # noqa: BLE001
            return []

    def compact_context(self, query: str, top_k: int = 5) -> str:
        """Genera contexto compacto con las reflexiones relevantes.

        Args:
            query: Consulta.
            top_k: Numero de reflexiones.

        Returns:
            Texto compacto (una linea por reflexion).
        """
        results = self.retrieve(query, top_k=top_k)
        lines = []
        for r in results:
            meta = r.get("metadata", {}) or {}
            refl = meta.get("reflection", "")
            if refl:
                lines.append(f"- {refl}")
        return "\n".join(lines)


__all__ = ["ReflectionMemory"]
