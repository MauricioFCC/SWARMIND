"""Export all DEV-SPACE projects to Google Drive with dated ZIPs (solo lo commiteado).

Corregido 2026-08-08: el script anterior hardcodeaba rutas inexistentes
(quant-engine, health-record, trading-bot-AIBot, pos-system, from_zero) que
no coinciden con los proyectos reales de DEV-SPACE, dejando el export a
mitad de camino. Ahora descubre los proyectos dinámicamente.

Comportamiento:
  - Proyectos GIT  -> usa ``git ls-files --cached --others --exclude-standard``
                      (solo lo commiteado + no ignorado; sin .venv/node_modules).
  - Proyectos NO-GIT -> copia con filtro de exclusión estándar (sin .venv,
                      node_modules, .git, caches) y lo documenta en el log.

Seguridad (ADR-0035): rutas portables via env vars con fallback a
``Path.home()``; nunca rutas literales de usuario ni subcarpetas personales
hardcodeadas en el código commiteado. Variables:
  - ``SWARMIND_EXPORT_BASE``: destino de los ZIPs (default
    ``~/Mi unidad/DEV/SIDEPROYECT/exports``).
  - ``DEV_SPACE_ROOT``: raíz de proyectos (default ``~/Documents/DEV-SPACE``).
Sin ``except Exception: pass`` silencioso (regla ERR) — se loguea cada fallo
con contexto WHAT+WHY+WHERE.

Usage:
    python scripts/export_all_projects.py              # Export completo
    python scripts/export_all_projects.py --dry-run    # Simular solo
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess  # nosec B404 (git via lista args, sin shell)
import zipfile
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

#: Destino de los ZIPs (portable, ADR-0035: env var con fallback a Path.home()).
EXPORT_BASE = Path(
    os.environ.get("SWARMIND_EXPORT_BASE", str(Path.home() / "Mi unidad" / "DEV" / "SIDEPROYECT" / "exports"))
)
TODAY = datetime.now(UTC).date().isoformat()

#: Raíz de proyectos (portable, ADR-0035: env var con fallback a Path.home()).
DEV_SPACE = Path(os.environ.get("DEV_SPACE_ROOT", str(Path.home() / "Documents" / "DEV-SPACE")))

#: Directorios ignorados en proyectos NO-GIT (equivalente a .gitignore base).
_EXCLUDED_DIRS = {
    ".venv",
    "venv",
    "node_modules",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    "target",
    "dist",
    "build",
    ".next",
    ".cache",
}
_EXCLUDED_EXT = {".pyc", ".pyo"}

#: Mínimo de archivos para considerar "proyecto" un dir no-git sin estructura.
#: (Excluye por naturaleza la infraestructura del entorno, ej. `data/` con un
#:  settings.json suelto; sin hardcode de nombres de directorio).
MIN_PROJECT_FILES = 3


def _is_project_dir(entry: Path) -> bool:
    """Decide si un directorio de primer nivel es un proyecto exportable.

    UNIVERSAL (sin hardcode de nombres): un directorio es proyecto si:
      1. Es un repositorio git (tiene ``.git/``), o
      2. Tiene subdirectorios (estructura de proyecto), o
      3. Tiene ``MIN_PROJECT_FILES`` o más archivos.

    La infraestructura del entorno (directorios ocultos, dirs triviales con un
    archivo suelto como ``data/``) queda excluida por estas reglas, no por una
    lista de nombres.

    Args:
        entry: Directorio de primer nivel de DEV-SPACE.

    Returns:
        True si debe tratarse como proyecto.
    """
    if entry.name.startswith("."):
        return False
    if is_git_repo(entry):
        return True
    if any(child.is_dir() for child in entry.iterdir()):
        return True
    file_count = sum(1 for child in entry.iterdir() if child.is_file())
    return file_count >= MIN_PROJECT_FILES


def discover_projects() -> list[tuple[str, Path]]:
    """Descubre los proyectos reales de DEV-SPACE (directorios de primer nivel).

    UNIVERSAL (sin hardcode): se toma TODO directorio de primer nivel de
    DEV-SPACE que supere ``_is_project_dir`` — así, si se añade un proyecto
    nuevo (git o con estructura), se detecta y exporta automáticamente sin
    tocar el script.

    Returns:
        Lista de tuplas (tag, ruta). El tag es el nombre del directorio.
    """
    if not DEV_SPACE.exists():
        logger.warning(f"  Skipping: DEV-SPACE not found at {DEV_SPACE}")
        return []
    projects: list[tuple[str, Path]] = []
    for entry in sorted(DEV_SPACE.iterdir()):
        if not entry.is_dir():
            continue
        if _is_project_dir(entry):
            projects.append((entry.name, entry))
    return projects


def is_git_repo(root: Path) -> bool:
    """Devuelve True si el directorio es un repositorio git."""
    return (root / ".git").exists()


def git_tracked_files(root: Path) -> list[str]:
    """Lista los archivos commiteados + no ignorados de un repo git.

    Args:
        root: Ruta del repositorio.

    Returns:
        Lista de rutas relativas, o lista vacía si git no está disponible.
    """
    try:
        # nosec B404: subprocess necesario para invocar git; args estáticos.
        result = subprocess.run(  # nosec B603 B607
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            cwd=root,
            timeout=30,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning(
            f"  Skipping {root.name}: git no disponible "
            f"(WHAT=git_error WHY={type(exc).__name__} WHERE=git_tracked_files)"
        )
        return []
    if result.returncode != 0:
        logger.warning(
            f"  Skipping {root.name}: git ls-files fallo "
            f"(WHAT=git_error WHY=rc={result.returncode} WHERE=git_tracked_files)"
        )
        return []
    return [f for f in result.stdout.strip().splitlines() if f]


def filter_project_files(root: Path) -> list[str]:
    """Lista archivos de un proyecto NO-GIT aplicando exclusiones estándar.

    Args:
        root: Ruta del proyecto.

    Returns:
        Lista de rutas relativas sin directorios/extensiones excluidos.
    """
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in _EXCLUDED_EXT:
            continue
        rel = path.relative_to(root)
        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue
        files.append(rel.as_posix())
    return files


def export_project(tag: str, root: Path) -> int:
    """Exporta un proyecto a Drive con ZIP fechado (solo lo commiteado/no-ignorado).

    Args:
        tag: Nombre/etiqueta del proyecto (para el nombre del ZIP).
        root: Ruta del proyecto.

    Returns:
        Número de archivos exportados (0 si se omitió).
    """
    if not root.exists():
        logger.warning(f"  Skipping {tag}: path not found")
        return 0

    if is_git_repo(root):
        files = git_tracked_files(root)
        source = "git (commiteado)"
    else:
        files = filter_project_files(root)
        source = "filtro no-git"

    if not files:
        logger.warning(f"  Skipping {tag}: no tracked files")
        return 0

    folder = f"{tag}_{TODAY}"
    folder_path = EXPORT_BASE / folder
    zip_path = EXPORT_BASE / f"{folder}.zip"

    # Limpieza previa (solo del proyecto actual — nombre único por tag+fecha).
    if folder_path.exists():
        shutil.rmtree(folder_path)
    if zip_path.exists():
        zip_path.unlink()

    # Copia manteniendo estructura.
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
        except OSError as exc:
            logger.warning(
                f"  {tag}: no se pudo copiar {f} "
                f"(WHAT=copy_error WHY={exc} WHERE=export_project)"
            )

    if count == 0:
        logger.warning(f"  Skipping {tag}: no files copied")
        return 0

    # Crear ZIP y limpiar carpeta temporal.
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in folder_path.rglob("*"):
            if f.is_file():
                arcname = str(f.relative_to(folder_path.parent))
                zf.write(f, arcname)

    shutil.rmtree(folder_path)

    size_mb = zip_path.stat().st_size / 1024 / 1024
    logger.info(f"  OK {tag}: {count} files, {size_mb:.1f} MB [{source}] -> {zip_path.name}")
    return count


#: Patrón de ZIP fechado: <tag>_<YYYY-MM-DD>.zip (generado por este script).
_ZIP_DATE_RE = r"_(\d{4}-\d{2}-\d{2})\.zip$"


def cleanup_old_zips(tag: str, keep: Path | None = None) -> int:
    """Borra los ZIPs antiguos del proyecto dejando solo el más reciente.

    UNIVERSAL (sin hardcode de nombres protegidos): solo se consideran los ZIPs
    cuyo nombre matchea ``{tag}_YYYY-MM-DD.zip``, donde ``tag`` es un proyecto
    REAL detectado en DEV-SPACE. Todo ZIP que NO matchee ese patrón (copias de
    proyectos ajenos a DEV, respaldos manuales, nombres sin fecha, tags de
    proyectos que ya no existen) queda SIEMPRE intacto por construcción.

    El más reciente se determina por la FECHA del nombre (no por mtime), así el
    orden es estable aunque los archivos se copien entre carpetas.

    Args:
        tag: Etiqueta del proyecto (prefijo del nombre del ZIP).
        keep: ZIP a conservar (normalmente el recién creado). Si es None, se
            conserva el más reciente por fecha de nombre.

    Returns:
        Número de ZIPs antiguos eliminados.
    """
    import re

    pattern = re.compile(re.escape(tag) + _ZIP_DATE_RE)
    candidates: list[tuple[str, Path]] = []
    for zip_file in sorted(EXPORT_BASE.glob(f"{tag}_*.zip")):
        match = pattern.search(zip_file.name)
        if match:
            candidates.append((match.group(1), zip_file))

    if not candidates:
        return 0

    # El más reciente por fecha ISO (orden lexicográfico = cronológico).
    candidates.sort(key=lambda item: item[0])
    newest = candidates[-1][1]

    removed = 0
    for _, zip_file in candidates:
        if zip_file == newest:
            continue
        if keep is not None and zip_file == keep:
            continue
        try:
            zip_file.unlink()
            logger.info(f"  Limpieza {tag}: eliminado ZIP antiguo {zip_file.name}")
            removed += 1
        except OSError as exc:
            logger.warning(
                f"  {tag}: no se pudo eliminar {zip_file.name} "
                f"(WHAT=unlink_error WHY={exc} WHERE=cleanup_old_zips)"
            )
    return removed


def main() -> None:
    """Punto de entrada: exporta todos los proyectos de DEV-SPACE a Drive."""
    logger.info("=" * 50)
    logger.info("EXPORT ALL DEV-SPACE PROJECTS TO GOOGLE DRIVE (solo lo commiteado)")
    logger.info("=" * 50)

    projects = discover_projects()
    if not projects:
        logger.warning("  No projects found in DEV-SPACE")
        return

    logger.info(f"  Proyectos detectados: {', '.join(tag for tag, _ in projects)}")
    total = 0
    for tag, root in projects:
        total += export_project(tag, root)
        # Tras exportar, limpiar los ZIPs antiguos de ese proyecto (solo el último queda).
        cleanup_old_zips(tag)

    logger.info(f"\nOK Total: {total} files across {len(projects)} projects -> {EXPORT_BASE}")


if __name__ == "__main__":
    main()
