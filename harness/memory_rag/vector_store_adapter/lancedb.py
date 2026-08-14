"""Adaptador LanceDB para el paquete ``vector_store_adapter``.

Extraido mecanicamente de ``vector_store_adapter.py`` (regla AGR < 500
lineas). Contiene ``LanceDBAdapter``, la implementacion por defecto en
produccion que envuelve el cliente nativo de LanceDB.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from .base import VectorStoreAdapter
from .models import SearchResult

logger = logging.getLogger("harness.memory_rag.vector_store_adapter")


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
        now = datetime.now(UTC).isoformat()
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
