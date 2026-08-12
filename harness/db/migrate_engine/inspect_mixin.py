"""DB Migration Engine inspect mixin — scan, detect y stats.

Extraccion mecanica del modulo original
``harness/db/migrate_engine.py`` (sin cambios de logica ni firmas):
scan_imports, detect_format, get_stats, _import_lancedb y _human_size.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.db.migrate_discovery import (
    detect_format,
    probe_db,
)

from .constants import _get_current_collections

logger = logging.getLogger("harness.db.migrate_engine")


class _InspectMixin:
    """Mixin con inspeccion de imports, formatos y estadisticas."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_imports(self) -> list[dict[str, Any]]:
        """
        Escanea import_dir en busca de bases LanceDB legacy.

        Usa descubrimiento recursivo de directorios.

        Returns:
            Lista de dicts con: path, name, collections[], estimated_size,
            estimated_size_human.
        """
        imports: list[dict[str, Any]] = []
        import_path = Path(self.import_dir)

        if not import_path.exists():
            logger.debug("Directorio de import no existe: %s", self.import_dir)
            return imports

        # RECURSIVO: descubrir todas las BDs en subdirectorios
        for entry in sorted(import_path.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name
            if name.startswith(("_", ".")):
                continue

            info = probe_db(str(entry))
            if info is not None:
                imports.append(info)
                logger.info("Import detectado: %s (%d colecciones)", name, len(info["collections"]))

        return imports

    def detect_format(self, db_path: str) -> dict[str, Any]:
        """
        Inspecciona una base LanceDB y la compara con las colecciones actuales.

        Args:
            db_path: Ruta a la base de datos LanceDB.

        Returns:
            Dict con status, collections, differences.
        """
        current = _get_current_collections()
        return detect_format(db_path, current)

    def get_stats(self, db_path: str | None = None) -> dict[str, Any]:
        """
        Estadisticas de una base LanceDB.

        Args:
            db_path: Ruta a la BD (default: target_dir = harness/db/lancedb/).

        Returns:
            Dict con: total_chunks, collections[], size_bytes, size_human,
            last_modified, path.
        """
        path = db_path or self.target_dir
        db_path_obj = Path(path)

        if not db_path_obj.exists():
            return {
                "total_chunks": 0,
                "collections": [],
                "size_bytes": 0,
                "size_human": "0 B",
                "last_modified": "",
                "path": path,
                "error": "Base de datos no encontrada",
            }

        lancedb = self._import_lancedb()
        if lancedb is None:
            return {
                "total_chunks": 0,
                "collections": [],
                "size_bytes": 0,
                "size_human": "0 B",
                "last_modified": "",
                "path": path,
                "error": "LanceDB no instalado",
            }

        try:
            db = lancedb.connect(str(db_path_obj))
        except Exception as exc:  # noqa: BLE001
            return {
                "total_chunks": 0,
                "collections": [],
                "size_bytes": 0,
                "size_human": "0 B",
                "last_modified": "",
                "path": path,
                "error": str(exc),
            }

        tables = db.list_tables().tables
        total_chunks = 0
        collections_info: list[dict[str, Any]] = []

        for name in sorted(tables):
            try:
                tbl = db.open_table(name)
                count = tbl.count_rows()
                total_chunks += count
                last_up = ""
                if count > 0:
                    try:
                        last_row = tbl.head(count).to_pylist()[-1]
                        last_up = last_row.get("created_at", "")
                    except Exception as _exc:  # noqa: BLE001
                        logger.warning("migrate_engine: %s", _exc)
                collections_info.append(
                    {
                        "name": name,
                        "count": count,
                        "last_updated": last_up,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                collections_info.append(
                    {
                        "name": name,
                        "count": -1,
                        "error": str(exc),
                    }
                )

        # Tamano en disco
        size_bytes = sum(f.stat().st_size for f in db_path_obj.rglob("*") if f.is_file())

        # Ultima modificacion
        last_modified = ""
        mod_times = [
            f.stat().st_mtime for f in db_path_obj.rglob("*") if f.is_file()
        ]
        if mod_times:
            last_modified = datetime.fromtimestamp(
                max(mod_times), tz=UTC
            ).isoformat()

        return {
            "total_chunks": total_chunks,
            "collections": collections_info,
            "size_bytes": size_bytes,
            "size_human": self._human_size(size_bytes),
            "last_modified": last_modified,
            "path": str(db_path_obj),
        }

    # ------------------------------------------------------------------
    # Internal — import helpers
    # ------------------------------------------------------------------

    def _import_lancedb(self):
        """Lazy import of lancedb; returns module or None."""
        if self._lancedb_module is None:
            try:
                import lancedb  # type: ignore[import-untyped]
                self._lancedb_module = lancedb
            except ImportError:
                self._lancedb_module = False  # sentinel: already tried
        return self._lancedb_module if self._lancedb_module is not False else None

    # ------------------------------------------------------------------
    # Internal — utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        """Formatea bytes a representacion legible."""
        if size_bytes == 0:
            return "0 B"
        units = ("B", "KB", "MB", "GB")
        size = float(size_bytes)
        for unit in units:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
