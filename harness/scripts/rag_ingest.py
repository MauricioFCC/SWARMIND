#!/usr/bin/env python3
"""
Standalone RAG ingestion script.

Scans a project directory for source files, chunks them, and ingests
them into the LanceDB ``rag_chunks`` collection.

Usage:
    python harness/scripts/rag_ingest.py                     # ingiere todo el proyecto
    python harness/scripts/rag_ingest.py --dir src/           # solo un directorio
    python harness/scripts/rag_ingest.py --stats              # muestra stats sin ingerir
    python harness/scripts/rag_ingest.py --dry-run            # simula sin escribir
    python harness/scripts/rag_ingest.py --verbose            # progreso detallado
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Asegurar que el proyecto raÃ­z estÃ¡ en sys.path
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent.parent
sys.path.insert(1, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _show_stats() -> None:
    """Muestra estadisticas de la BD RAG sin ingerir."""
    try:
        from harness.memory_rag.lance_vector_store import LanceVectorStore
        store = LanceVectorStore()
        colls = store.list_collections()
        logger.info("")
        logger.info("  Colecciones disponibles: %s", colls)
        if "rag_chunks" in colls:
            try:
                stats = store.get_collection_stats("rag_chunks")
                logger.info("  Coleccion 'rag_chunks':")
                logger.info("    Items: %d", stats.get("item_count", 0))
                logger.info("    Ultima actualizacion: %s", stats.get("last_updated", "N/A"))
            except Exception as exc:  # noqa: BLE001
                logger.info("  Coleccion 'rag_chunks' existe (stats no disponibles: %s)", exc)
        else:
            logger.info("  Coleccion 'rag_chunks' no existe. Ejecuta '!rag ingest' para crearla.")
        logger.info("")
    except ImportError as exc:
        logger.error("  LanceDB no disponible: %s", exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        logger.error("  Error al obtener stats: %s", exc)
        sys.exit(1)


def _ingest(
    directory: str,
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    """Ingiere archivos fuente desde *directory* en la BD RAG."""
    from harness.memory_rag.doc_ingester import ingest_project_directory

    target = Path(directory).resolve()
    if not target.is_dir():
        logger.error("  Directorio no encontrado: %s", target)
        sys.exit(1)

    logger.info("")
    logger.info("  \U0001f4da RAG Ingestion")
    logger.info("  %s\u2500%s", "\u2500" * 60, "\u2500" * 20)
    logger.info("  Directorio: %s", target)
    logger.info("  Dry-run:    %s", dry_run)
    logger.info("  Verbose:    %s", verbose)
    logger.info("")

    if dry_run:
        # Solo contar archivos, sin ingerir
        from harness.memory_rag.doc_ingester import RAG_EXCLUDE, RAG_EXTENSIONS
        count = 0
        for fpath in sorted(target.rglob("*")):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in RAG_EXTENSIONS:
                continue
            if any(part in RAG_EXCLUDE for part in fpath.parts):
                continue
            if any(part.startswith(".") for part in fpath.parts):
                continue
            if fpath.name == ".gitkeep":
                continue
            count += 1
            if verbose:
                logger.info("  [DRY-RUN] %s", fpath.relative_to(target))
        logger.info("")
        logger.info("  Dry-run: %d archivos detectados (no se ingirio nada)", count)
        return

    start = time.time()
    try:
        stats = ingest_project_directory(
            str(target),
            show_progress=verbose,
        )
        elapsed = time.time() - start

        files = stats.get("files_processed", 0)
        chunks = stats.get("chunks_inserted", 0)
        errors = stats.get("errors", 0)

        logger.info("")
        logger.info("  \u2705 RAG ingest completado")
        logger.info("  %s\u2500%s", "\u2500" * 30, "\u2500" * 10)
        logger.info("  Archivos procesados: %d", files)
        logger.info("  Chunks insertados:   %d", chunks)
        logger.info("  Errores:             %d", errors)
        logger.info("  Tiempo:              %.1fs", elapsed)

        if errors:
            logger.warning("  \u26a0\ufe0f  Hubo %d errores. Revisa los logs para mas detalles.", errors)

    except Exception as e:  # noqa: BLE001
        logger.error("  \u274c Error en RAG ingest: %s", e)
        sys.exit(1)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="RAG ingestion: chunk and vectorize project source files.",
    )
    parser.add_argument(
        "--dir", "-d",
        default=None,
        help="Directorio a escanear (default: raiz del proyecto)",
    )
    parser.add_argument(
        "--stats", "-s",
        action="store_true",
        help="Muestra estadisticas de la BD RAG sin ingerir",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Simula sin escribir en la BD",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Muestra progreso detallado por archivo",
    )

    args = parser.parse_args()

    if args.stats:
        _show_stats()
        return

    directory = args.dir or str(_PROJECT_ROOT)
    _ingest(directory, dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
