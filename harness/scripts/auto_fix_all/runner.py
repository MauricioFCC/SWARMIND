"""auto_fix_all runner — orquestador principal ``fix_file`` y ``main``.

Extraccion mecanica del modulo original
``harness/scripts/auto_fix_all.py`` (sin cambios de logica ni firmas):
el CLI exacto (main con --dry-run) se preserva en ``__main__.py``.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from .constants import PROJECT_ROOT, SCOPES
from .docstrings import _fix_missing_docstrings
from .prints import _ensure_logger_setup, _replace_print_with_logging
from .todos import _fix_todos
from .typehints import _fix_missing_type_hints

logger = logging.getLogger("harness.scripts.auto_fix_all")


# =============================================================================
# Main orchestrator
# =============================================================================

def fix_file(filepath: Path, dry_run: bool = False) -> dict[str, int]:
    """Fix all issues in a single file. Returns stats."""
    stats: dict[str, int] = {
        "prints_to_logging": 0,
        "type_hints": 0,
        "docstrings": 0,
        "todos": 0,
    }

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            original_content = f.read()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"  [SKIP] {filepath.name}: {e}")
        return stats

    content = original_content
    rel_path = str(filepath.relative_to(PROJECT_ROOT))

    # 1. Fix print() -> logging
    if ".py" in filepath.suffix:
        content, pcount = _replace_print_with_logging(content, str(filepath))
        if pcount > 0:
            content = _ensure_logger_setup(content, str(filepath))
        stats["prints_to_logging"] = pcount

        # 2. Fix type hints
        content, tcount = _fix_missing_type_hints(content, str(filepath))
        stats["type_hints"] = tcount

        # 3. Fix docstrings
        content, dcount = _fix_missing_docstrings(content, str(filepath))
        stats["docstrings"] = dcount

    # 4. Fix TODOs
    content, tocount = _fix_todos(content, str(filepath))
    stats["todos"] = tocount

    if content != original_content:
        if dry_run:
            logger.info(f"  [DRY-RUN] {rel_path}: print={pcount} hints={tcount} docstrings={dcount} todos={tocount}")
        else:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"  [FIXED] {rel_path}: print={pcount} hints={tcount} docstrings={dcount} todos={tocount}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"  [ERROR] {rel_path}: {e}")
    else:
        total = pcount + tcount + dcount + tocount
        if total > 0:
            logger.info(f"  [ALREADY] {rel_path}: {total} suspected (no changes needed)")

    return stats


def main() -> None:
    """Main."""
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        logger.info("Modo DRY-RUN — no se modificaran archivos")
    else:
        logger.info("Corrigiendo bugs menores...")
    logger.info("")

    total_stats: dict[str, int] = {
        "prints_to_logging": 0,
        "type_hints": 0,
        "docstrings": 0,
        "todos": 0,
    }
    files_processed = 0
    files_changed = 0

    # Collect all Python files in scope
    py_files: list[Path] = []
    for scope in SCOPES:
        if scope.exists():
            py_files.extend(scope.rglob("*.py"))

    # Filter out __pycache__
    py_files = [f for f in py_files if "__pycache__" not in str(f)]

    for filepath in py_files:
        stats = fix_file(filepath, dry_run=dry_run)
        total_stats["prints_to_logging"] += stats["prints_to_logging"]
        total_stats["type_hints"] += stats["type_hints"]
        total_stats["docstrings"] += stats["docstrings"]
        total_stats["todos"] += stats["todos"]
        files_processed += 1
        if any(v > 0 for v in stats.values()):
            files_changed += 1

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"RESUMEN: {files_processed} archivos procesados, {files_changed} modificados")
    logger.info(f"  print() → logger.info(): {total_stats['prints_to_logging']}")
    logger.info(f"  Type hints agregados:   {total_stats['type_hints']}")
    logger.info(f"  Docstrings agregados:   {total_stats['docstrings']}")
    logger.info(f"  TODO/FIXME marcados:    {total_stats['todos']}")
    logger.info("=" * 60)

    if dry_run:
        logger.info("\nEjecuta sin --dry-run para aplicar los cambios.")
