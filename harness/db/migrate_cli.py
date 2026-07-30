"""
DB Migration CLI — Interfaz de línea de comandos para migración de bases de datos.

Extraída de migrate_db.py para separar concerns.
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from harness.db.migrate_engine import DBMigrator

logger = logging.getLogger(__name__)


def _print_result(result: dict[str, Any]) -> None:
    """Pretty-print resultado de migracion."""
    if result["migrated_collections"]:
        logger.info("  [OK] Migradas: %s", ", ".join(result["migrated_collections"]))
    if result["created"]:
        logger.info("  [NEW] Creadas: %s", ", ".join(result["created"]))
    if result["skipped"]:
        for s in result["skipped"]:
            logger.info("  [SKIP] %s", s)
    if result["errors"]:
        for e in result["errors"]:
            logger.info("  [ERROR] %s", e)
    if result.get("backup_path"):
        logger.info("  [BACKUP] %s", result["backup_path"])


def main() -> None:
    """Entry point para ejecucion directa: python harness/db/migrate_db.py."""
    parser = argparse.ArgumentParser(
        description="Migrador de bases de datos LanceDB del Harness",
    )
    parser.add_argument("--scan", action="store_true",
                        help="Escanea imports disponibles en harness/db/import/")
    parser.add_argument("--migrate", type=str, nargs="?", const="all",
                        help="Migra imports (omitiendo ruta = todos; o pasa ruta especifica)")
    parser.add_argument("--stats", type=str, nargs="?", const="",
                        help="Muestra estadisticas de la BD activa (o ruta especifica)")
    parser.add_argument("--rollback", type=str,
                        help="Restaura desde un directorio _backup_<timestamp>/")
    parser.add_argument("--detect", type=str,
                        help="Detecta formato de una BD especifica (ruta)")

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
            logger.info("\n[DB] Bases de datos detectadas (%d):", len(imports))
            for imp in imports:
                logger.info(
                    "  * %s: %d colecciones, %s",
                    imp["name"], len(imp["collections"]), imp["estimated_size_human"],
                )
                for coll in imp["collections"]:
                    logger.info("    - %s", coll)
        else:
            logger.info("\n[DB] No se detectaron bases de datos en import/")
        return

    # --- migrate ---
    if args.migrate:
        if args.migrate == "all":
            imports = migrator.scan_imports()
            if not imports:
                logger.info("\n[DB] No hay bases para migrar.")
                return
            for imp in imports:
                logger.info("\n[DB] Migrando: %s...", imp["name"])
                result = migrator.migrate(imp["path"])
                _print_result(result)
        else:
            logger.info("\n[DB] Migrando: %s...", args.migrate)
            result = migrator.migrate(args.migrate)
            _print_result(result)
        return

    # --- stats ---
    if args.stats is not None:
        db_path = args.stats if args.stats else None
        stats = migrator.get_stats(db_path)
        logger.info("\n[DB] Estadisticas de BD:")
        logger.info("  Path:   %s", stats.get("path", "N/A"))
        logger.info("  Chunks: %d", stats["total_chunks"])
        logger.info("  Tamano: %s", stats.get("size_human", "N/A"))
        logger.info("  Ultima mod: %s", stats.get("last_modified", "N/A"))
        logger.info("  Colecciones:")
        for coll in stats["collections"]:
            if coll["count"] >= 0:
                logger.info("    * %s: %d registros", coll["name"], coll["count"])
            else:
                logger.info("    * %s: ERROR %s", coll["name"], coll.get("error", ""))
        if "error" in stats:
            logger.info("  [ERROR] %s", stats["error"])
        return

    # --- rollback ---
    if args.rollback:
        success = migrator.rollback(args.rollback)
        if success:
            logger.info("\n[DB] Base restaurada desde: %s", args.rollback)
        else:
            logger.info("\n[DB] Error al restaurar desde: %s", args.rollback)
        return

    # --- detect ---
    if args.detect:
        info = migrator.detect_format(args.detect)
        logger.info("\n[DB] Formato: %s", info["status"])
        logger.info("  Colecciones (%d): %s", len(info["collections"]), ", ".join(info["collections"]))
        if info["differences"]:
            logger.info("  Diferencias (%d):", len(info["differences"]))
            for d in info["differences"]:
                logger.info("    %s", d)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
