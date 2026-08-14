"""DB Migration Engine migrate mixin — migracion, rollback y archivo.

Extraccion mecanica del modulo original
``harness/db/migrate_engine.py`` (sin cambios de logica ni firmas):
migrate, rollback, _backup_import, _archive_old_collection,
_migrate_collection y _reconstruct_metadata.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from harness.memory_rag.lance_migration import (
    adapt_vector,
)

from .constants import _get_current_collections

logger = logging.getLogger("harness.db.migrate_engine")


class _MigrateMixin:
    """Mixin con el pipeline de migracion, rollback y archivo."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def migrate(
        self,
        import_path: str,
        target_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Migra una base de datos desde import_path hacia target_path.

        Pipeline:
          1. Backup automatico del import a _backup_<timestamp>/
          2. Conecta BD origen y destino
          3. Para cada coleccion compartida -> lee datos, transforma, inserta
          4. Colecciones nuevas -> creadas vacias
          5. Colecciones obsoletas -> archivadas a JSON

        Args:
            import_path: Ruta a la BD legacy.
            target_path: Ruta destino (default: harness/db/lancedb/).

        Returns:
            Dict con: migrated_collections[], skipped[], errors[], created[],
            backup_path.
        """
        target = target_path or self.target_dir
        result: dict[str, Any] = {
            "migrated_collections": [],
            "skipped": [],
            "errors": [],
            "created": [],
            "backup_path": None,
        }

        lancedb = self._import_lancedb()
        if lancedb is None:
            result["errors"].append("LanceDB no esta instalado. pip install lancedb")
            return result

        # 1. Backup automatico
        backup_path = self._backup_import(import_path)
        if backup_path:
            result["backup_path"] = backup_path
            logger.info("Backup creado en: %s", backup_path)
        else:
            logger.warning("No se pudo crear backup automatico")

        current = _get_current_collections()

        # 2. Conectar origen
        try:
            old_db = lancedb.connect(import_path)
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"No se pudo abrir BD origen '{import_path}': {exc}")
            return result

        old_tables = set(old_db.list_tables().tables)
        new_tables = set(current.keys())

        # Abrir el store destino (LanceVectorStore crea colecciones al vuelo)
        from harness.memory_rag.lance_vector_store import LanceVectorStore

        target_store = LanceVectorStore(target)

        # --- 3. Migrar colecciones compartidas ---
        shared = old_tables & new_tables
        if not shared:
            logger.info("No hay colecciones compartidas entre origen y destino.")

        for name in sorted(shared):
            try:
                count = self._migrate_collection(
                    old_db=old_db,
                    target_store=target_store,
                    collection_name=name,
                )
                result["migrated_collections"].append(f"{name} ({count} registros)")
                logger.info("Migrada '%s': %d registros", name, count)
            except Exception as exc:
                err_msg = f"{name}: {exc}"
                result["errors"].append(err_msg)
                logger.exception("Error migrando '%s'", name)

        # --- 4. Crear colecciones nuevas ---
        for name in sorted(new_tables - old_tables):
            try:
                target_store.create_collection(name)
                result["created"].append(name)
                logger.info("Creada coleccion nueva: '%s'", name)
            except Exception as exc:  # noqa: BLE001
                result["errors"].append(f"Error creando '{name}': {exc}")

        # --- 5. Archivar colecciones obsoletas ---
        for name in sorted(old_tables - new_tables):
            try:
                archive_path = self._archive_old_collection(old_db, name)
                result["skipped"].append(f"{name} -> archivada")
                logger.warning(
                    "Coleccion '%s' archivada en %s (ya no existe en schema nuevo)",
                    name,
                    archive_path,
                )
            except Exception as exc:  # noqa: BLE001
                result["errors"].append(f"Error archivando '{name}': {exc}")

        return result

    def rollback(self, backup_path: str) -> bool:
        """
        Restaura una base de datos desde un backup previo a migracion.

        Args:
            backup_path: Ruta al directorio _backup_<timestamp>/.

        Returns:
            True si se restauro correctamente.
        """
        backup = Path(backup_path)
        if not backup.exists():
            logger.error("Backup no encontrado: %s", backup_path)
            return False

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        restore_name = f"_restored_{timestamp}"
        restore_path = backup.parent / restore_name

        try:
            shutil.copytree(str(backup), str(restore_path))
            logger.info("Backup restaurado en: %s", restore_path)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Error restaurando backup: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal — backup / archive
    # ------------------------------------------------------------------

    def _backup_import(self, import_path: str) -> str | None:
        """Copia import_path a _backup_<timestamp>/."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_dir = str(Path(import_path).parent / f"_backup_{timestamp}")
        try:
            shutil.copytree(import_path, backup_dir)
            return backup_dir
        except Exception as exc:  # noqa: BLE001
            logger.error("Error creando backup: %s", exc)
            return None

    def _archive_old_collection(self, old_db: Any, collection_name: str) -> str:
        """
        Archiva una coleccion que ya no existe en el schema nuevo.
        Lee todos sus datos y los guarda como JSON en _archived/.
        """
        Path(self.archive_dir).mkdir(parents=True, exist_ok=True)
        tbl = old_db.open_table(collection_name)
        row_count = tbl.count_rows()
        data = tbl.head(row_count).to_pylist() if row_count > 0 else []

        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        archive_name = f"{collection_name}_{ts}.json"
        archive_path = str(Path(self.archive_dir) / archive_name)

        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)

        logger.info(
            "Coleccion '%s' archivada: %s (%d registros)",
            collection_name,
            archive_path,
            len(data),
        )
        return archive_path

    # ------------------------------------------------------------------
    # Internal — migration core
    # ------------------------------------------------------------------

    def _migrate_collection(
        self,
        old_db: Any,
        target_store: Any,
        collection_name: str,
    ) -> int:
        """
        Migra UNA coleccion desde la BD vieja a la nueva.

        Lee todas las filas de la coleccion origen, transforma cada fila al
        schema actual y las reinserta usando LanceVectorStore.insert().

        Returns:
            Numero de registros migrados.
        """
        old_tbl = old_db.open_table(collection_name)

        row_count = old_tbl.count_rows()
        if row_count == 0:
            logger.info("Coleccion '%s' vacia -- sin datos que migrar.", collection_name)
            return 0
        rows = old_tbl.head(row_count).to_pylist()

        if not rows:
            logger.info("Coleccion '%s' vacia - sin datos que migrar.", collection_name)
            return 0

        vectors_list: list[np.ndarray] = []
        metadata_list: list[dict[str, Any]] = []

        for row in rows:
            vec_raw = row.get("vector")
            if vec_raw is not None:
                vec = np.array(vec_raw, dtype=np.float32).flatten()
            else:
                vec = np.zeros(384, dtype=np.float32)
            vectors_list.append(vec)

            meta = self._reconstruct_metadata(row)
            metadata_list.append(meta)

        if not vectors_list:
            return 0

        # Verificar dimension de vectores
        dims = {v.shape[0] for v in vectors_list}
        if len(dims) > 1:
            logger.warning(
                "Coleccion '%s': dimension de vectores variable %s. "
                "Se truncara/padeara a %d.",
                collection_name,
                dims,
                max(dims),
            )
            target_dim = max(dims)
            vectors_list = [adapt_vector(v, target_dim) for v in vectors_list]

        vectors = np.stack(vectors_list)

        expected_dim = getattr(target_store, "_embedding_dim", 384)
        if vectors.shape[1] != expected_dim:
            logger.warning(
                "Coleccion '%s': vectores dim %d != esperada %d. Adaptando.",
                collection_name,
                vectors.shape[1],
                expected_dim,
            )

        ids = target_store.insert(collection_name, vectors, metadata_list)
        return len(ids)

    @staticmethod
    def _reconstruct_metadata(row: dict[str, Any]) -> dict[str, Any]:
        """
        Reconstruye un dict de metadata desde una fila de LanceDB legacy.

        Toma el campo metadata (JSON string) como base y le incorpora
        los campos top-level que NO son columnas estandar de LanceDB.
        """
        meta_raw = row.get("metadata", "{}")
        if isinstance(meta_raw, str):
            try:
                meta: dict[str, Any] = json.loads(meta_raw)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        elif isinstance(meta_raw, dict):
            meta = dict(meta_raw)
        else:
            meta = {}

        STANDARD_COLS = {"id", "vector", "metadata", "created_at"}
        for key, val in row.items():
            if key in STANDARD_COLS:
                continue
            if isinstance(val, str):
                try:
                    meta[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    meta[key] = val
            else:
                meta[key] = val

        return meta
