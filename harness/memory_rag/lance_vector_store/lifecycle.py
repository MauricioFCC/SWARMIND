"""Operaciones de ciclo de vida del store (borrado, limpieza, cierre).

Extraido de ``core.py`` (regla AGR: modulo < 500 lineas). Agrupa las
operaciones que destruyen estado: ``delete``, ``delete_collection``, ``clear``
y ``close``. La logica por backend vive en ``backends.py``.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..lance_schemas import DEFAULT_COLLECTIONS
from .backends import _MemoryBackendMixin
from .exceptions import VectorStoreError
from .models import _Collection

logger = logging.getLogger("harness.memory_rag.lance_vector_store")


class _LifecycleMixin(_MemoryBackendMixin):
    """Metodos de ciclo de vida compartidos por los backends del store.

    Hereda del mixin in-memory para que ``delete``/``clear`` puedan operar sobre
    ``_mem_collections``; el store compone dos bases (SOL: <=2).
    """

    def _init_storage(self) -> None:
        """Intenta abrir LanceDB; si no hay motor, cae al fallback in-memory."""
        if self._backend == "memory":
            # Backend memory = in-memory puro: no intentar LanceDB (evita
            # depender de un lancedb mockeado/parcial en tests y CI).
            self._init_memory_collections()
            return
        if self._connect_lancedb():
            return
        self._init_memory_collections()

    def _connect_lancedb(self) -> bool:
        """Conecta LanceDB; False si corresponde usar el fallback in-memory."""
        lancedb = self._try_import_lancedb()
        if lancedb is None:
            if not self._allow_fallback:
                raise ImportError(self._missing_lancedb_message())
            return False
        try:
            Path(self.db_path).mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(self.db_path)
            self._lancedb_available = True
            logger.info("LanceVectorStore connected to %s", self.db_path)
            self._ensure_lancedb_collections()
            return True
        except Exception as exc:
            if not self._allow_fallback:
                raise RuntimeError(self._connect_error_message(exc)) from exc
            logger.warning(
                "LanceDB connect failed (%s); fallback in-memory "
                "(allow_fallback=True). NO RECOMENDADO para produccion.",
                exc,
            )
            return False

    @staticmethod
    def _missing_lancedb_message() -> str:
        """Mensaje accionable cuando falta LanceDB y no hay fallback."""
        return (
            "LanceDB no esta instalado. Es OBLIGATORIO para el backend 'lancedb'.\n"
            "  pip install lancedb   (o: pip install \"Swarmind-harness[lancedb]\")\n"
            "  python harness/scripts/init.py\n"
            "Alternativas: backend='memory' (tests) o RuscaDB (DLL nativa)."
        )

    def _connect_error_message(self, exc: Exception) -> str:
        """Mensaje accionable cuando LanceDB no puede conectar."""
        return (
            f"LanceDB no pudo conectarse en {self.db_path}: {exc}\n"
            "Verifica que LanceDB este instalado y la ruta sea valida.\n"
            '  pip install "Swarmind-harness[lancedb]"\n'
            "  python harness/scripts/init.py"
        )

    def _init_memory_collections(self) -> None:
        """Inicializa el fallback in-memory con las colecciones por defecto."""
        logger.warning(
            "LanceVectorStore usando fallback in-memory (dict + numpy). "
            "Rendimiento limitado y sin persistencia."
        )
        self._lancedb_available = False
        self._db = None
        for name, info in DEFAULT_COLLECTIONS.items():
            self._mem_collections[name] = _Collection(
                name=name,
                schema_def=info["schema"],
                last_updated=datetime.now(UTC).isoformat(),
            )

    def delete_collection(self, name: str) -> None:
        """Elimina una coleccion completa.

        Args:
            name: Nombre de la coleccion.

        Raises:
            VectorStoreError: Si LanceDB no puede eliminar la tabla.
        """
        if self._lancedb_available and self._db is not None:
            try:
                self._db.drop_table(name)
            except Exception as exc:
                raise VectorStoreError(
                    f"Failed to drop LanceDB table '{name}': {exc}"
                ) from exc
        elif name in self._mem_collections:
            del self._mem_collections[name]

    def delete(self, collection: str, ids: list[str]) -> int:
        """Elimina registros por id (paridad con ``VectorStorePort``).

        Args:
            collection: Coleccion destino.
            ids: Ids logicos a borrar.

        Returns:
            Numero de registros eliminados (0 si la coleccion no existe).
        """
        if not ids:
            return 0
        if self._lancedb_available and self._db is not None:
            return self._delete_lancedb(collection, ids)
        col: Any = self._mem_collections.get(collection)
        if col is None:
            return 0
        removed = 0
        for rid in ids:
            if rid in col.items:
                del col.items[rid]
                removed += 1
        return removed

    def clear(self) -> None:
        """Elimina todas las colecciones y restaura las de por defecto."""
        if self._lancedb_available and self._db is not None:
            for name in self._db.list_tables().tables:
                try:
                    self._db.drop_table(name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("lance_vector_store: clear drop fallo: %s", exc)
        self._mem_collections.clear()
        for name, info in DEFAULT_COLLECTIONS.items():
            self._mem_collections[name] = _Collection(
                name=name,
                schema_def=info["schema"],
                last_updated=datetime.now(UTC).isoformat(),
            )

    def close(self) -> None:
        """Libera la conexion subyacente.

        LanceDB no expone ``close``; el fallback in-memory no tiene recursos
        externos. El metodo existe para cumplir ``VectorStorePort`` y permitir
        cleanup homogeneo entre adaptadores.
        """
        self._db = None
        self._lancedb_available = False


__all__ = ["_LifecycleMixin"]
