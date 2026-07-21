"""
Export AGENTIC to Google Drive mirror with dated ZIP.

Crea:
    C:\\Users\\USUARIO\\Mi unidad\\DEV\\SIDEPROYECT\\exports\\AGENTIC_YYYY-MM-DD.zip

Cada proyecto tiene su propio ZIP con fecha en el mismo directorio:
    core-quant-engine-2026-07-20.zip
    HistoriaClinica-2026-07-20.zip
    AGENTIC_YYYY-MM-DD.zip  ← este script

Usage:
    python scripts/export_to_drive.py              # Export + ZIP (default)
    python scripts/export_to_drive.py --keep       # Keep temp folder after ZIP
    python scripts/export_to_drive.py --dry-run    # Simulate only
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

_EXPORT_BASE = Path(
    r"C:\Users\USUARIO\Mi unidad\DEV\SIDEPROYECT\exports"
)

# Date-based naming matching other projects
_TODAY = date.today().isoformat()  # 2026-07-20
_PROJECT = "AGENTIC"
_FOLDER_NAME = f"{_PROJECT}_{_TODAY}"  # AGENTIC_2026-07-20
_ZIP_NAME = f"{_FOLDER_NAME}.zip"       # AGENTIC_2026-07-20.zip

_EXPORT_DIR = _EXPORT_BASE / _FOLDER_NAME
_ZIP_PATH = _EXPORT_BASE / _ZIP_NAME


def _get_tracked_files() -> list[Path]:
    """Get all files tracked by git in the repository."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, cwd=_ROOT, check=True,
    )
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
    Export repository to dated folder + auto-ZIP.

    Args:
        dry_run: If True, only simulate.

    Returns:
        Number of files exported.
    """
    logger.info("=" * 60)
    logger.info(f"📤 {_PROJECT} EXPORT TO GOOGLE DRIVE")
    logger.info(f"   Source: {_ROOT}")
    logger.info(f"   Folder: {_EXPORT_DIR}")
    logger.info(f"   ZIP:    {_ZIP_PATH}")
    logger.info(f"   Dry run: {dry_run}")
    logger.info("=" * 60)

    if not _EXPORT_BASE.exists():
        logger.error(f"❌ Export base not found: {_EXPORT_BASE}")
        return 0

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

    # Clean previous folder with same date (from prior run)
    if _EXPORT_DIR.exists():
        logger.info(f"\n🧹 Cleaning existing folder: {_EXPORT_DIR}")
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

    logger.info(f"\n✅ Exported: {count} files to {_EXPORT_DIR}")
    if errors:
        logger.warning(f"⚠️  Errors: {errors}")

    return count


def create_zip() -> Path:
    """
    Create dated ZIP and optionally remove temp folder.

    Returns:
        Path to the created ZIP file.
    """
    if not _EXPORT_DIR.exists():
        logger.error(f"❌ Export folder not found: {_EXPORT_DIR}")
        return _ZIP_PATH

    # Remove old ZIP with same name
    if _ZIP_PATH.exists():
        _ZIP_PATH.unlink()

    logger.info(f"\n📦 Creating ZIP: {_ZIP_PATH}")

    # Create ZIP with the folder itself as root (not just its contents)
    # This ensures when unzipped, everything is inside AGENTIC_YYYY-MM-DD/
    base_dir = _EXPORT_DIR.parent
    folder_name = _EXPORT_DIR.name
    shutil.make_archive(
        str(_ZIP_PATH.with_suffix("")),
        "zip",
        base_dir,
        folder_name,  # only this folder, not the whole base_dir
    )
    logger.info(f"   ✅ ZIP created ({_ZIP_PATH.stat().st_size / 1024**2:.1f} MB)")

    return _ZIP_PATH


def _cleanup_folder() -> None:
    """Remove the temporary export folder after successful ZIP."""
    if _EXPORT_DIR.exists():
        logger.info(f"🧹 Removing temp folder: {_EXPORT_DIR}")
        shutil.rmtree(_EXPORT_DIR)


def main():
    parser = argparse.ArgumentParser(
        description=f"Export {_PROJECT} to Google Drive mirror with dated ZIP"
    )
    parser.add_argument(
        "--keep", action="store_true",
        help="Keep temp export folder after creating ZIP"
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

    if not args.dry_run:
        zip_path = create_zip()
        if not args.keep:
            _cleanup_folder()

        if zip_path.exists():
            logger.info(f"\n🎉 Export complete!")
            logger.info(f"   📍 {zip_path}")
            logger.info(f"   📊 {count} files in {_FOLDER_NAME}")


if __name__ == "__main__":
    main()
