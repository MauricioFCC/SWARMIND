"""
Export AGENTIC to Google Drive mirror.

Copia el repositorio AGENTIC a:
    C:\\Users\\USUARIO\\Mi unidad\\DEV\\SIDEPROYECT\\exports\\AGENTIC

Usa git archive para exportar solo archivos trackeados (limpio).
Opcional: comprime a ZIP con timestamp.

Usage:
    python scripts/export_to_drive.py              # Export fresh copy
    python scripts/export_to_drive.py --zip         # Export + ZIP
    python scripts/export_to_drive.py --dry-run     # Simulate only
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent  # AGENTIC root

_EXPORT_BASE = Path(
    r"C:\Users\USUARIO\Mi unidad\DEV\SIDEPROYECT\exports"
)
_EXPORT_DIR = _EXPORT_BASE / "AGENTIC"


def _get_tracked_files() -> list[Path]:
    """Get all files tracked by git in the repository."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, cwd=_ROOT, check=True,
    )
    # Also include untracked files that are not ignored
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True, cwd=_ROOT, check=True,
    )
    files = set(result.stdout.strip().splitlines())
    files.update(untracked.stdout.strip().splitlines())
    return [Path(f) for f in sorted(files) if f]


def _should_skip(path: Path) -> bool:
    """Check if a file should be skipped from export."""
    skip_patterns = [
        ".venv", "__pycache__", ".pytest_cache", ".mypy_cache",
        ".ruff_cache", ".git", ".coverage", "coverage.xml",
        "*.pyc", "*.pyo", "*.log", "*.bak", "*.orig",
        ".env", ".env.local",
    ]
    for part in path.parts:
        for pattern in skip_patterns:
            if pattern.startswith("*") and path.name.endswith(pattern[1:]):
                return True
            if part == pattern:
                return True
    return False


def export(dry_run: bool = False) -> int:
    """
    Export AGENTIC repository to Google Drive mirror.

    Args:
        dry_run: If True, only simulate.

    Returns:
        Number of files exported.
    """
    logger.info("=" * 60)
    logger.info("📤 AGENTIC EXPORT TO GOOGLE DRIVE")
    logger.info(f"   Source: {_ROOT}")
    logger.info(f"   Dest:   {_EXPORT_DIR}")
    logger.info(f"   Dry run: {dry_run}")
    logger.info("=" * 60)

    if not _EXPORT_BASE.exists():
        logger.error(f"❌ Export base not found: {_EXPORT_BASE}")
        return 0

    # Get files to export
    files = _get_tracked_files()
    files = [f for f in files if not _should_skip(f)]
    logger.info(f"\n📦 Files to export: {len(files)}")

    if dry_run:
        logger.info("\n📋 Sample files (first 20):")
        for f in files[:20]:
            logger.info(f"   • {f}")
        if len(files) > 20:
            logger.info(f"   ... and {len(files) - 20} more")
        return len(files)

    # Clean destination
    if _EXPORT_DIR.exists():
        logger.info(f"\n🧹 Cleaning: {_EXPORT_DIR}")
        shutil.rmtree(_EXPORT_DIR)

    # Copy files maintaining structure
    count = 0
    errors = 0
    for file_path in files:
        src = _ROOT / file_path
        dst = _EXPORT_DIR / file_path
        if not src.exists():
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            count += 1
        except Exception as e:
            logger.warning(f"   ⚠️  Failed: {file_path} — {e}")
            errors += 1

    logger.info(f"\n✅ Exported: {count} files")
    if errors:
        logger.warning(f"⚠️  Errors: {errors}")

    return count


def create_zip() -> Path:
    """
    Create a timestamped ZIP archive of the export.

    Returns:
        Path to the created ZIP file.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"AGENTIC_{timestamp}.zip"
    zip_path = _EXPORT_BASE / zip_name

    logger.info(f"\n📦 Creating ZIP: {zip_path}")
    shutil.make_archive(
        str(zip_path.with_suffix("")),  # remove .zip for make_archive
        "zip",
        _EXPORT_DIR,
    )
    logger.info(f"   ✅ ZIP created: {zip_path}")
    return zip_path


def main():
    parser = argparse.ArgumentParser(
        description="Export AGENTIC to Google Drive mirror"
    )
    parser.add_argument(
        "--zip", action="store_true",
        help="Also create timestamped ZIP archive"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simulate without copying"
    )
    args = parser.parse_args()

    count = export(dry_run=args.dry_run)
    if count == 0:
        logger.error("❌ No files exported")
        sys.exit(1)

    if args.zip and not args.dry_run:
        create_zip()

    logger.info("\n🎉 Export complete!")
    if not args.dry_run:
        logger.info(f"   📍 {_EXPORT_DIR}")
        logger.info(f"   📊 {count} files synced")


if __name__ == "__main__":
    main()
