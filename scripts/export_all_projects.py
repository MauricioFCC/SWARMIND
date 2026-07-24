"""Export all projects to Google Drive with dated ZIPs."""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

EXPORT_BASE = Path(r"C:\Users\USUARIO\Mi unidad\DEV\SIDEPROYECT\exports")
TODAY = date.today().isoformat()

# SOLO proyectos AGENTIC - NO agregar proyectos externos
# Los archivos ZIP de proyectos NO listados aqui NO deben eliminarse
PROJECTS = [
    ("AGENTIC", Path(__file__).resolve().parent.parent),
    ("CQE", Path(r"C:\Users\USUARIO\Documents\DEV-SPACE\core-quant-engine")),
    ("HC", Path(r"C:\Users\USUARIO\Documents\DEV-SPACE\Historia Clinica")),
    ("Onyx", Path(r"C:\Users\USUARIO\Documents\DEV-SPACE\Onyx-Quan-AIBot")),
    ("PDV", Path(r"C:\Users\USUARIO\Documents\DEV-SPACE\PDV Basic")),
    ("Alfa", Path(r"C:\Users\USUARIO\Documents\DEV-SPACE\de_0_a_Alfa")),
]

# Tags de proyectos AGENTIC (para NO eliminar archivos externos)
_KNOWN_TAGS = {p[0] for p in PROJECTS}


def export_project(tag: str, root: Path) -> int:
    """Export a project using git archive (fast)."""
    if not root.exists():
        logger.warning(f"  Skipping {tag}: path not found")
        return 0
    
    # Use git to get tracked files (fast, clean)
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, cwd=root, timeout=30,
        )
        files = [f for f in result.stdout.strip().splitlines() if f]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning(f"  Skipping {tag}: not a git repository")
        return 0
    
    if not files:
        logger.warning(f"  Skipping {tag}: no tracked files")
        return 0
    
    folder = f"{tag}_{TODAY}"
    folder_path = EXPORT_BASE / folder
    zip_path = EXPORT_BASE / f"{folder}.zip"
    
    # Clean previous
    # Safety: solo eliminar archivos de proyectos AGENTIC conocidos
    if tag not in _KNOWN_TAGS:
        logger.warning(f"  Safety: {tag} not in known projects, skipping cleanup")
        return 0
    
    if folder_path.exists():
        shutil.rmtree(folder_path)
    if zip_path.exists():
        zip_path.unlink()
    
    # Copy files maintaining structure
    count = 0
    for f in files:
        src = root / f
        dst = folder_path / f
        if not src.exists():
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            count += 1
        except Exception:
            pass
    
    if count == 0:
        logger.warning(f"  Skipping {tag}: no files copied")
        return 0
    
    # Create ZIP
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in folder_path.rglob('*'):
            if f.is_file():
                arcname = str(f.relative_to(folder_path.parent))
                zf.write(f, arcname)
    
    # Clean temp folder
    shutil.rmtree(folder_path)
    
    size_mb = zip_path.stat().st_size / 1024 / 1024
    logger.info(f"  ✅ {tag}: {count} files, {size_mb:.1f} MB -> {zip_path.name}")
    return count


def main():
    logger.info("=" * 50)
    logger.info("EXPORT ALL PROJECTS TO GOOGLE DRIVE")
    logger.info("=" * 50)
    
    total = 0
    for tag, root in PROJECTS:
        c = export_project(tag, root)
        total += c
    
    logger.info(f"\n✅ Total: {total} files across {len(PROJECTS)} projects")


if __name__ == "__main__":
    main()
