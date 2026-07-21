#!/usr/bin/env python3
"""
Cleanup — Mantenimiento automatico del proyecto.

Elimina archivos temporales, cache, y residuos de compilacion.
Disenado como script temporal para ejecucion periodica.

Uso:
    python harness/scripts/cleanup.py                    # Cleanup completo
    python harness/scripts/cleanup.py --dry-run          # Preview
    python harness/scripts/cleanup.py --cache-only       # Solo cache
    python harness/scripts/cleanup.py --temp-only        # Solo temporales
    python harness/scripts/cleanup.py --aged-days 7      # Archivos >7 dias sin modificar
"""

from __future__ import annotations

import argparse
import logging
import shutil
import time
from pathlib import Path
from typing import List

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent


def _size_str(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return "%.1f %s" % (size_bytes, unit)
        size_bytes /= 1024
    return "%.1f GB" % size_bytes


def _find_cached_dirs() -> List[Path]:
    """Find __pycache__ directories."""
    return list(ROOT.rglob("__pycache__"))


def _find_temp_patterns() -> List[Path]:
    """Find .pyc, .pyo, .log, .tmp files."""
    patterns = ["*.pyc", "*.pyo", "*.log", "*.tmp", "*.temp", "*.swp", "*.swo"]
    files = []
    for pattern in patterns:
        files.extend(ROOT.rglob(pattern))
    return files


def _find_aged_files(days: int) -> List[Path]:
    """Find files not modified in N days."""
    cutoff = time.time() - (days * 86400)
    aged = []
    for f in ROOT.rglob("*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            # Skip .git files
            if ".git" in str(f):
                continue
            aged.append(f)
    return aged


def cleanup(
    dry_run: bool = False,
    cache: bool = True,
    temp: bool = True,
    aged_days: int = 0,
) -> dict:
    """Run cleanup and return stats."""
    stats = {"dirs_removed": 0, "files_removed": 0, "bytes_freed": 0}

    if cache:
        for d in _find_cached_dirs():
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) if not dry_run else 0
            if dry_run:
                logger.info("  [DRY-RUN] Would remove %s/ (%s)", d.relative_to(ROOT), _size_str(size))
            else:
                shutil.rmtree(d, ignore_errors=True)
                stats["dirs_removed"] += 1
                stats["bytes_freed"] += size

    if temp:
        for f in _find_temp_patterns():
            size = f.stat().st_size if not dry_run else 0
            if dry_run:
                logger.info("  [DRY-RUN] Would remove %s (%s)", f.relative_to(ROOT), _size_str(size))
            else:
                f.unlink(missing_ok=True)
                stats["files_removed"] += 1
                stats["bytes_freed"] += size

    if aged_days > 0:
        for f in _find_aged_files(aged_days):
            size = f.stat().st_size if not dry_run else 0
            if dry_run:
                logger.info("  [DRY-RUN] Would remove %s (aged %dd, %s)", f.relative_to(ROOT), aged_days, _size_str(size))
            else:
                f.unlink(missing_ok=True)
                stats["files_removed"] += 1
                stats["bytes_freed"] += size

    return stats


def main():
    parser = argparse.ArgumentParser(description="Project cleanup")
    parser.add_argument("--dry-run", action="store_true", help="Preview")
    parser.add_argument("--cache-only", action="store_true", help="Only __pycache__")
    parser.add_argument("--temp-only", action="store_true", help="Only temp files")
    parser.add_argument("--aged-days", type=int, default=0, help="Remove files aged N+ days")
    args = parser.parse_args()

    do_cache = not args.temp_only
    do_temp = not args.cache_only
    aged = args.aged_days

    logger.info("Cleanup %s (dry-run=%s)", ROOT, args.dry_run)

    stats = cleanup(
        dry_run=args.dry_run,
        cache=do_cache,
        temp=do_temp,
        aged_days=aged,
    )

    if args.dry_run:
        logger.info(
            "Would remove %d dirs and %d files (%s)",
            stats["dirs_removed"], stats["files_removed"],
            _size_str(stats["bytes_freed"]),
        )
    else:
        logger.info(
            "Removed %d cache dirs, %d temp files (%s freed)",
            stats["dirs_removed"], stats["files_removed"],
            _size_str(stats["bytes_freed"]),
        )


if __name__ == "__main__":
    main()
