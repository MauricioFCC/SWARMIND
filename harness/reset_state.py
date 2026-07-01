"""
Harness reset — clean all runtime state for a fresh start.

Removes:
  - Vector database (harness/db/lancedb/)
  - Prompt archives (harness/evolve_loop/prompt_archive/)
  - Auto-generated skills (.opencode/skills/auto/)
  - Scheduled jobs (harness/orchestrator/scheduler_jobs.yaml)
  - Python cache files (__pycache__/, *.pyc)

Run this before copying the harness to a new project.
"""
import os
import shutil
import sys
from pathlib import Path
import logging
logger = logging.getLogger(__name__)


def banner(msg: str) -> None:
    """Banner."""
    logger.info(f"  {msg}")


def rm_dir(path: Path) -> None:
    """Rm dir."""
    if path.exists() and path.is_dir():
        shutil.rmtree(path)
        banner(f"Eliminado: {path}")
    else:
        banner(f"(no existe, se omite): {path}")


def rm_file(path: Path) -> None:
    """Rm file."""
    if path.exists() and path.is_file():
        path.unlink()
        banner(f"Eliminado: {path}")
    else:
        banner(f"(no existe, se omite): {path}")


def empty_dir_keep_gitkeep(path: Path) -> None:
    """Remove all files inside a directory except .gitkeep."""
    if not path.exists() or not path.is_dir():
        return
    for item in path.iterdir():
        if item.name == ".gitkeep":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    banner(f"Vaciado: {path} (conservado .gitkeep)")


def clean_pycache(root: Path) -> None:
    """Recursively remove all __pycache__ directories and .pyc files."""
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d))
                count += 1
                dirnames.remove(d)
        for f in filenames:
            if f.endswith(".pyc"):
                os.remove(os.path.join(dirpath, f))
                count += 1
    if count:
        banner(f"Cache de Python eliminado: {count} archivos/dirs")
    else:
        banner("(sin cache de Python)")


def main() -> None:
    """Main."""
    project_root = Path(__file__).resolve().parent.parent  # AGENTIC/

    logger.info("")
    banner("[Harness reset] Limpiando estado...")
    logger.info("")

    # 1. Vector database (new name)
    rm_dir(project_root / "harness" / "db" / "lancedb")
    # Legacy path cleanup
    legacy_db = project_root / "harness" / "db" / "lancedb_store"
    if legacy_db.exists():
        shutil.rmtree(legacy_db)
        banner(f"Eliminado (legacy): {legacy_db}")

    # 2. Prompt archive (backups de prompts evolucionados)
    rm_dir(project_root / "harness" / "evolve_loop" / "prompt_archive")

    # 3. Auto-generated skills
    auto_skills = project_root / ".opencode" / "skills" / "auto"
    empty_dir_keep_gitkeep(auto_skills)

    # 4. Scheduled jobs
    scheduler_jobs = (
        project_root / "harness" / "orchestrator" / "scheduler_jobs.yaml"
    )
    if scheduler_jobs.exists():
        scheduler_jobs.write_text("jobs: []\n", encoding="utf-8")
        banner(f"Vaciado: {scheduler_jobs.name}")
    else:
        banner(f"(no existe, se omite): scheduler_jobs.yaml")

    # 5. Python cache
    clean_pycache(project_root / "harness")
    clean_pycache(project_root / ".opencode")

    logger.info("")
    banner("[OK] Harness resetado. Listo para pegar en nuevo proyecto.")
    logger.info("")
    banner("Proximo paso: copia harness/ y .opencode/ a tu proyecto")
    banner("y ejecuta: python harness/scripts/init.py")
    logger.info("")


if __name__ == "__main__":
    main()
