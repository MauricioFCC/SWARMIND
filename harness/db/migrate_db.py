"""
Migrador de bases de datos LanceDB entre versiones del harness.

Modo de uso:
  1. Copia tu BD anterior a: harness/db/import/<nombre>/
  2. Ejecuta: python harness/db/migrate_db.py
  3. El script detecta, migra y confirma

O automáticamente al ejecutar: python harness/scripts/init.py
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (resolved relative to this file's location)
# ---------------------------------------------------------------------------

HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IMPORT_DIR = os.path.join(HARNESS_DIR, "db", "import")
DEFAULT_TARGET_DIR = os.path.join(HARNESS_DIR, "db", "lancedb")
DEFAULT_ARCHIVE_DIR = os.path.join(HARNESS_DIR, "db", "_archived")


def _get_current_collections() -> Dict[str, Any]:
    """Lazy-import DEFAULT_COLLECTIONS to avoid circular imports at module level."""
    from harness.memory_rag.lance_vector_store import DEFAULT_COLLECTIONS

    return DEFAULT_COLLECTIONS


# ---------------------------------------------------------------------------
# DBMigrator
# ---------------------------------------------------------------------------


class DBMigrator:
    """
    Migrador de bases de datos LanceDB entre versiones del harness.

    Detecta BDs viejas en ``harness/db/import/``, compara sus schemas contra
    el formato actual (``LanceVectorStore.DEFAULT_COLLECTIONS``) y migra los
    datos automáticamente, con backup previo y soporte de rollback.
    """

    def __init__(
        self,
        import_dir: Optional[str] = None,
        target_dir: Optional[str] = None,
        archive_dir: Optional[str] = None,
    ) -> None:
        self.import_dir = import_dir or DEFAULT_IMPORT_DIR
        self.target_dir = target_dir or DEFAULT_TARGET_DIR
        self.archive_dir = archive_dir or DEFAULT_ARCHIVE_DIR
        self._lancedb_module: Any = None  # lazy import

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_imports(self) -> List[Dict[str, Any]]:
        """
        Escanea ``import_dir`` en busca de bases LanceDB legacy.

        Returns:
            Lista de dicts con: path, name, collections[], estimated_size,
            estimated_size_human.
        """
        imports: List[Dict[str, Any]] = []
        import_path = Path(self.import_dir)

        if not import_path.exists():
            logger.debug("Directorio de import no existe: %s", self.import_dir)
            return imports

        for entry in sorted(import_path.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name
            # Skip internal/private dirs
            if name.startswith("_") or name.startswith("."):
                continue

            info = self._probe_db(str(entry))
            if info is not None:
                imports.append(info)
                logger.info("Import detectado: %s (%d colecciones)", name, len(info["collections"]))

        return imports

    def detect_format(self, db_path: str) -> Dict[str, Any]:
        """
        Inspecciona una base LanceDB y la compara con las colecciones actuales.

        La comparación se hace a nivel de nombres de colección. Las diferencias
        de schema interno se resuelven durante la migración (``migrate()``).

        Args:
            db_path: Ruta a la base de datos LanceDB.

        Returns:
            Dict con:
              - status: "compatible" | "needs_migration" | "unknown"
              - collections: list[str]
              - differences: list[str] (descripciones legibles)
        """
        current = _get_current_collections()
        result: Dict[str, Any] = {
            "status": "compatible",
            "collections": [],
            "differences": [],
        }

        lancedb = self._import_lancedb()
        if lancedb is None:
            return {
                "status": "unknown",
                "collections": [],
                "differences": ["LanceDB no instalado"],
            }

        try:
            db = lancedb.connect(db_path)
        except Exception as exc:
            return {
                "status": "unknown",
                "collections": [],
                "differences": ["No se pudo abrir la BD: {}".format(exc)],
            }

        old_tables = set(db.list_tables().tables)
        new_tables = set(current.keys())

        result["collections"] = sorted(old_tables)

        # --- Colecciones que ya no existen en el schema actual ---
        removed = old_tables - new_tables
        if removed:
            result["differences"].append(
                "Colecciones obsoletas (ya no existen en schema actual): {}"
                .format(", ".join(sorted(removed)))
            )
            result["status"] = "needs_migration"

        # --- Verificar que las colecciones compartidas se pueden leer ---
        for name in sorted(old_tables & new_tables):
            try:
                tbl = db.open_table(name)
                _ = tbl.head(1).to_pylist()  # solo verifica que se puede leer
            except Exception as exc:
                result["differences"].append(
                    "'{}': error al leer datos: {}".format(name, exc)
                )
                result["status"] = "unknown"

        # --- Colecciones nuevas que no existian ---
        new_only = new_tables - old_tables
        if new_only:
            result["differences"].append(
                "Nuevas colecciones a crear: {}".format(", ".join(sorted(new_only)))
            )

        return result

    def migrate(
        self,
        import_path: str,
        target_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Migra una base de datos desde ``import_path`` hacia ``target_path``.

        Pipeline:
          1. Backup automático del import a ``_backup_<timestamp>/``
          2. Conecta BD origen y destino
          3. Para cada colección compartida → lee datos, transforma, inserta
          4. Colecciones nuevas → creadas vacías
          5. Colecciones obsoletas → archivadas a JSON

        Args:
            import_path: Ruta a la BD legacy.
            target_path: Ruta destino (default: harness/db/lancedb/).

        Returns:
            Dict con: migrated_collections[], skipped[], errors[], created[],
            backup_path.
        """
        target = target_path or self.target_dir
        result: Dict[str, Any] = {
            "migrated_collections": [],
            "skipped": [],
            "errors": [],
            "created": [],
            "backup_path": None,
        }

        lancedb = self._import_lancedb()
        if lancedb is None:
            result["errors"].append("LanceDB no está instalado. pip install lancedb")
            return result

        # 1. Backup automático
        backup_path = self._backup_import(import_path)
        if backup_path:
            result["backup_path"] = backup_path
            logger.info("Backup creado en: %s", backup_path)
        else:
            logger.warning("No se pudo crear backup automático")

        current = _get_current_collections()

        # 2. Conectar origen
        try:
            old_db = lancedb.connect(import_path)
        except Exception as exc:
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
                logger.info("Creada colección nueva: '%s'", name)
            except Exception as exc:
                result["errors"].append(f"Error creando '{name}': {exc}")

        # --- 5. Archivar colecciones obsoletas ---
        for name in sorted(old_tables - new_tables):
            try:
                archive_path = self._archive_old_collection(old_db, name)
                result["skipped"].append(f"{name} → archivada")
                logger.warning(
                    "Colección '%s' archivada en %s (ya no existe en schema nuevo)",
                    name,
                    archive_path,
                )
            except Exception as exc:
                result["errors"].append(f"Error archivando '{name}': {exc}")

        return result

    def rollback(self, backup_path: str) -> bool:
        """
        Restaura una base de datos desde un backup previo a migración.

        Copia el contenido del backup a un directorio de restauración
        dentro de ``import/``.

        Args:
            backup_path: Ruta al directorio _backup_<timestamp>/.

        Returns:
            True si se restauró correctamente.
        """
        backup = Path(backup_path)
        if not backup.exists():
            logger.error("Backup no encontrado: %s", backup_path)
            return False

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        restore_name = f"_restored_{timestamp}"
        restore_path = backup.parent / restore_name

        try:
            shutil.copytree(str(backup), str(restore_path))
            logger.info(
                "Backup restaurado en: %s",
                restore_path,
            )
            return True
        except Exception as exc:
            logger.error("Error restaurando backup: %s", exc)
            return False

    def get_stats(self, db_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Estadísticas de una base LanceDB.

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
        except Exception as exc:
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
        collections_info: List[Dict[str, Any]] = []

        for name in sorted(tables):
            try:
                tbl = db.open_table(name)
                count = tbl.count_rows()
                total_chunks += count
                # Last created_at in the table
                last_up = ""
                if count > 0:
                    try:
                        last_row = tbl.head(count).to_pylist()[-1]
                        last_up = last_row.get("created_at", "")
                    except Exception:
                        pass
                collections_info.append(
                    {
                        "name": name,
                        "count": count,
                        "last_updated": last_up,
                    }
                )
            except Exception as exc:
                collections_info.append(
                    {
                        "name": name,
                        "count": -1,
                        "error": str(exc),
                    }
                )

        # Tamaño en disco
        size_bytes = sum(f.stat().st_size for f in db_path_obj.rglob("*") if f.is_file())

        # Última modificación
        last_modified = ""
        mod_times = [
            f.stat().st_mtime for f in db_path_obj.rglob("*") if f.is_file()
        ]
        if mod_times:
            last_modified = datetime.fromtimestamp(
                max(mod_times), tz=timezone.utc
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

    def _probe_db(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Intenta abrir ``path`` como base LanceDB.
        Si tiene tablas, devuelve metadatos; si no, None.
        """
        lancedb = self._import_lancedb()
        if lancedb is None:
            return None

        try:
            db = lancedb.connect(path)
            tables = db.list_tables().tables
            if not tables:
                return None

            size = sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())
            return {
                "path": path,
                "name": os.path.basename(path),
                "collections": tables,
                "estimated_size": size,
                "estimated_size_human": self._human_size(size),
            }
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal — backup / archive
    # ------------------------------------------------------------------

    def _backup_import(self, import_path: str) -> Optional[str]:
        """Copia ``import_path`` a ``_backup_<timestamp>/``."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(
            os.path.dirname(import_path),
            f"_backup_{timestamp}",
        )
        try:
            shutil.copytree(import_path, backup_dir)
            return backup_dir
        except Exception as exc:
            logger.error("Error creando backup: %s", exc)
            return None

    def _archive_old_collection(self, old_db: Any, collection_name: str) -> str:
        """
        Archiva una colección que ya no existe en el schema nuevo.
        Lee todos sus datos y los guarda como JSON en ``_archived/``.
        """
        os.makedirs(self.archive_dir, exist_ok=True)
        tbl = old_db.open_table(collection_name)
        row_count = tbl.count_rows()
        data = tbl.head(row_count).to_pylist() if row_count > 0 else []

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_name = f"{collection_name}_{ts}.json"
        archive_path = os.path.join(self.archive_dir, archive_name)

        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)

        logger.info(
            "Colección '%s' archivada: %s (%d registros)",
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
        Migra UNA colección desde la BD vieja a la nueva.

        Lee todas las filas de la colección origen, transforma cada fila al
        schema actual y las reinserta usando ``LanceVectorStore.insert()``.

        Returns:
            Número de registros migrados.
        """
        old_tbl = old_db.open_table(collection_name)

        # Leer todas las filas (head() devuelve PyArrow Table; to_pylist() -> list[dict])
        row_count = old_tbl.count_rows()
        if row_count == 0:
            logger.info("Coleccion '%s' vacia -- sin datos que migrar.", collection_name)
            return 0
        rows = old_tbl.head(row_count).to_pylist()

        if not rows:
            logger.info("Colección '%s' vacía — sin datos que migrar.", collection_name)
            return 0

        vectors_list: List[np.ndarray] = []
        metadata_list: List[Dict[str, Any]] = []

        for row in rows:
            # --- Vector ---
            vec_raw = row.get("vector")
            if vec_raw is not None:
                vec = np.array(vec_raw, dtype=np.float32).flatten()
            else:
                vec = np.zeros(384, dtype=np.float32)
            vectors_list.append(vec)

            # --- Metadata reconstruida ---
            meta = self._reconstruct_metadata(row)
            metadata_list.append(meta)

        if not vectors_list:
            return 0

        # Verificar dimensión de vectores
        dims = {v.shape[0] for v in vectors_list}
        if len(dims) > 1:
            logger.warning(
                "Colección '%s': dimensión de vectores variable %s. "
                "Se truncará/padeará a %d.",
                collection_name,
                dims,
                max(dims),
            )
            # Uniformar a la dimensión más común
            target_dim = max(dims)
            vectors_list = [
                self._adapt_vector(v, target_dim) for v in vectors_list
            ]

        vectors = np.stack(vectors_list)

        # Verificar contra la dimensión esperada del store
        expected_dim = getattr(target_store, "_embedding_dim", 384)
        if vectors.shape[1] != expected_dim:
            logger.warning(
                "Colección '%s': vectores dim %d != esperada %d. Adaptando.",
                collection_name,
                vectors.shape[1],
                expected_dim,
            )

        # Insertar en el store destino
        ids = target_store.insert(collection_name, vectors, metadata_list)
        return len(ids)

    def _reconstruct_metadata(
        self,
        row: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Reconstruye un dict de metadata desde una fila de LanceDB legacy.

        Toma el campo ``metadata`` (JSON string) como base y le incorpora
        los campos top-level que NO son columnas estándar de LanceDB
        (``id``, ``vector``, ``metadata``, ``created_at``).

        No aplica defaults del schema porque los schemas declarativos en
        ``DEFAULT_COLLECTIONS`` a menudo no coinciden exactamente con las
        columnas reales de las tablas LanceDB (creadas via sample row).
        """
        # --- 1. Parsear metadata JSON base ---
        meta_raw = row.get("metadata", "{}")
        if isinstance(meta_raw, str):
            try:
                meta: Dict[str, Any] = json.loads(meta_raw)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        elif isinstance(meta_raw, dict):
            meta = dict(meta_raw)
        else:
            meta = {}

        # --- 2. Incorporar campos top-level (spread metadata) ---
        STANDARD_COLS = {"id", "vector", "metadata", "created_at"}
        for key, val in row.items():
            if key in STANDARD_COLS:
                continue
            # Intentar deserializar si es JSON string (listas, dicts)
            if isinstance(val, str):
                try:
                    meta[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    meta[key] = val
            else:
                meta[key] = val

        return meta

    # ------------------------------------------------------------------
    # Internal — utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _adapt_vector(vec: np.ndarray, target_dim: int) -> np.ndarray:
        """Truncar o padear un vector a una dimensión objetivo."""
        current_dim = vec.shape[0]
        if current_dim == target_dim:
            return vec
        if current_dim > target_dim:
            return vec[:target_dim]
        # pad with zeros
        padded = np.zeros(target_dim, dtype=np.float32)
        padded[:current_dim] = vec
        return padded

    @staticmethod
    def _default_for_type(field_type: str) -> Any:
        """Valor default según el tipo declarado en el schema."""
        defaults = {
            "string": "",
            "int": 0,
            "float": 0.0,
            "bool": False,
            "list<string>": [],
            "list<float>": [],
            "dict": {},
        }
        return defaults.get(field_type, "")

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        """Formatea bytes a representación legible."""
        if size_bytes == 0:
            return "0 B"
        units = ("B", "KB", "MB", "GB")
        size = float(size_bytes)
        for unit in units:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point para ejecución directa: ``python harness/db/migrate_db.py``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrador de bases de datos LanceDB del Harness",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Escanea imports disponibles en harness/db/import/",
    )
    parser.add_argument(
        "--migrate",
        type=str,
        nargs="?",
        const="all",
        help="Migra imports (omitiendo ruta = todos; o pasa ruta específica)",
    )
    parser.add_argument(
        "--stats",
        type=str,
        nargs="?",
        const="",
        help="Muestra estadísticas de la BD activa (o ruta específica)",
    )
    parser.add_argument(
        "--rollback",
        type=str,
        help="Restaura desde un directorio _backup_<timestamp>/",
    )
    parser.add_argument(
        "--detect",
        type=str,
        help="Detecta formato de una BD específica (ruta)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="[migrate] %(levelname)s %(message)s",
    )

    migrator = DBMigrator()

    # --- scan ---
    if args.scan:
        imports = migrator.scan_imports()
        if imports:
            print("\n[DB] Bases de datos detectadas ({}):".format(len(imports)))
            for imp in imports:
                print(
                    "  * {}: {} colecciones, {}".format(
                        imp["name"], len(imp["collections"]), imp["estimated_size_human"]
                    )
                )
                for coll in imp["collections"]:
                    print("    - {}".format(coll))
        else:
            print("\n[DB] No se detectaron bases de datos en import/")
        return

    # --- migrate ---
    if args.migrate:
        if args.migrate == "all":
            imports = migrator.scan_imports()
            if not imports:
                print("\n[DB] No hay bases para migrar.")
                return
            for imp in imports:
                print("\n[DB] Migrando: {}...".format(imp["name"]))
                result = migrator.migrate(imp["path"])
                _print_result(result)
        else:
            print("\n[DB] Migrando: {}...".format(args.migrate))
            result = migrator.migrate(args.migrate)
            _print_result(result)
        return

    # --- stats ---
    if args.stats is not None:
        db_path = args.stats if args.stats else None
        stats = migrator.get_stats(db_path)
        print("\n[DB] Estadisticas de BD:")
        print("  Path:   {}".format(stats.get("path", "N/A")))
        print("  Chunks: {}".format(stats["total_chunks"]))
        print("  Tamano: {}".format(stats.get("size_human", "N/A")))
        print("  Ultima mod: {}".format(stats.get("last_modified", "N/A")))
        print("  Colecciones:")
        for coll in stats["collections"]:
            if coll["count"] >= 0:
                print("    * {}: {} registros".format(coll["name"], coll["count"]))
            else:
                print("    * {}: ERROR {}".format(coll["name"], coll.get("error", "")))
        if "error" in stats:
            print("  [ERROR] {}".format(stats["error"]))
        return

    # --- rollback ---
    if args.rollback:
        success = migrator.rollback(args.rollback)
        if success:
            print("\n[DB] Base restaurada desde: {}".format(args.rollback))
        else:
            print("\n[DB] Error al restaurar desde: {}".format(args.rollback))
        return

    # --- detect ---
    if args.detect:
        info = migrator.detect_format(args.detect)
        print("\n[DB] Formato: {}".format(info["status"]))
        print("  Colecciones ({}): {}".format(len(info["collections"]), ", ".join(info["collections"])))
        if info["differences"]:
            print("  Diferencias ({}):".format(len(info["differences"])))
            for d in info["differences"]:
                print("    {}".format(d))
        return

    parser.print_help()


def _print_result(result: Dict[str, Any]) -> None:
    """Pretty-print resultado de migracion."""
    if result["migrated_collections"]:
        print("  [OK] Migradas: {}".format(", ".join(result["migrated_collections"])))
    if result["created"]:
        print("  [NEW] Creadas: {}".format(", ".join(result["created"])))
    if result["skipped"]:
        for s in result["skipped"]:
            print("  [SKIP] {}".format(s))
    if result["errors"]:
        for e in result["errors"]:
            print("  [ERROR] {}".format(e))
    if result.get("backup_path"):
        print("  [BACKUP] {}".format(result["backup_path"]))


if __name__ == "__main__":
    main()
