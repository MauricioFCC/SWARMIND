"""backup_to_gdrive.py — Backup local de DEV-SPACE a Google Drive del PC.

WHAT: Copia idempotente (robocopy /E, solo deltas) de cada proyecto de
DEV-SPACE a ``<drive>/DEV/SWARMIND-backup`` excluyendo junk (.venv,
node_modules, __pycache__, target, .pytest_cache).
WHY: 6 de los 11 proyectos commiteados NO tienen upstream remoto (git
100% local) y 5 ni siquiera tienen git — el unico respaldo es este
backup a Google Drive (resilience ante fallo de disco).
WHERE: Ejecucion manual o post-push; ``--dry-run`` para auditar el plan.

Uso:
    uv run -- python scripts/backup_to_gdrive.py --dry-run
    uv run -- python scripts/backup_to_gdrive.py
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("scripts.backup_to_gdrive")

# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
#: Ruta por defecto del workspace (SWARMIND/..).
DEFAULT_SRC = Path(r"C:\Users\USUARIO\Documents\DEV-SPACE")
#: Destino default en Google Drive (montado en C:\Users\USUARIO\Mi unidad).
DEFAULT_DEST = Path(r"C:\Users\USUARIO\Mi unidad\DEV\SWARMIND-backup")
#: Directorios junk excluidos de la copia.
DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".venv", "venv", "node_modules", "__pycache__", "target",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build",
    ".coverage", "htmlcov", ".next", ".turbo",
)
#: Piso de exit code de robocopy: >= 8 es error (0-7 = OK/warnings).
ROBOCOPY_ERROR_FLOOR = 8
#: Directorios propios que nunca se respaldan.
_SKIP_SELF: frozenset[str] = frozenset({"__pycache__", ".pytest_cache", "recovery"})
#: Proyectos con datos sensibles (salud/juridico/BD clientes): EXCLUIDOS por
#: defecto del backup a la nube (SEG); se incluyen solo con --include-sensitive.
SENSITIVE_PROJECTS: frozenset[str] = frozenset({
    "Historia Clinica", "JURIDICO", "DB caliche",
})


@dataclass(frozen=True)
class CopyEntry:
    """Una entrada del plan de copia.

    Attributes:
        src: Proyecto origen.
        dst: Destino en Google Drive.
        excludes: Directorios excluidos (robocopy /XD).
    """

    src: Path
    dst: Path
    excludes: tuple[str, ...]


@dataclass(frozen=True)
class BackupSummary:
    """Resumen del backup ejecutado.

    Attributes:
        copied: Proyectos copiados sin error (exit < 8).
        failed: Proyectos con error (exit >= 8).
        codes: Exit codes de robocopy en orden.
    """

    copied: int
    failed: int
    codes: tuple[int, ...]


def _discover_projects(
    root: Path, include_sensitive: bool = False
) -> list[Path]:
    """Descubre proyectos respaldables bajo ``root`` (dirs no-junk).

    Args:
        root: Directorio del workspace (p. ej. DEV-SPACE).
        include_sensitive: Incluir proyectos con datos sensibles (salud/
            juridico/BD clientes). Default False (SEG: opt-in explicito).

    Returns:
        Lista de directorios de proyecto (con o sin .git).
    """
    if not root.is_dir():
        raise FileNotFoundError(
            f"WHAT: workspace no encontrado: {root}. "
            "WHY: el backup necesita la raiz de proyectos. "
            "WHERE: _discover_projects"
        )
    projects: list[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name in _SKIP_SELF or child.name.startswith(("__", ".")):
            continue
        if not include_sensitive and child.name in SENSITIVE_PROJECTS:
            logger.info("backup: proyecto sensible excluido (SEG): %s", child.name)
            continue
        projects.append(child)
    return projects


def _plan_copy(
    projects: list[Path],
    dest: Path,
    excludes: tuple[str, ...],
) -> list[CopyEntry]:
    """Construye el plan de copia (src -> dest/<nombre>).

    Args:
        projects: Proyectos a respaldar.
        dest: Raiz de destino en Google Drive.
        excludes: Directorios junk a excluir.

    Returns:
        Lista de CopyEntry (una por proyecto).
    """
    return [
        CopyEntry(src=project, dst=dest / project.name, excludes=excludes)
        for project in projects
    ]


def _is_ok(code: int) -> bool:
    """True si el exit code de robocopy es OK (0-7)."""
    return code < ROBOCOPY_ERROR_FLOOR


def _robocopy_code(src: Path, dst: Path, excludes: tuple[str, ...]) -> int:
    """Ejecuta robocopy /E con excludes y retorna su exit code.

    Args:
        src: Proyecto origen.
        dst: Directorio destino (se crea si falta).
        excludes: Directorios a excluir (/XD).

    Returns:
        Exit code de robocopy (0-7 OK; >= 8 error).
    """
    dst.mkdir(parents=True, exist_ok=True)
    cmd = ["robocopy", str(src), str(dst), "/E", "/NFL", "/NDL", "/NJH", "/NP"]
    for exclude in excludes:
        cmd += ["/XD", str(src / exclude)]
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=False,
    )
    return result.returncode


def run_copy(
    plan: list[CopyEntry],
    runner=None,
) -> BackupSummary:
    """Ejecuta el plan de copia (indep. del runner para tests).

    Args:
        plan: Entradas a copiar.
        runner: Callable (src, dst, excludes) -> int; default robocopy.

    Returns:
        BackupSummary con contadores y codes.
    """
    if runner is None:
        runner = _robocopy_code
    copied = failed = 0
    codes: list[int] = []
    for entry in plan:
        code = runner(entry.src, entry.dst, entry.excludes)
        codes.append(code)
        if _is_ok(code):
            copied += 1
            logger.info("backup OK %s -> %s (robocopy %d)", entry.src.name, entry.dst, code)
        else:
            failed += 1
            logger.error(
                "backup FAIL %s -> %s (robocopy %d; WHY: >= %d). WHERE: run_copy",
                entry.src.name, entry.dst, code, ROBOCOPY_ERROR_FLOOR,
            )
    return BackupSummary(copied=copied, failed=failed, codes=tuple(codes))


def main(argv: list[str] | None = None) -> int:
    """CLI del backup: audita el plan (--dry-run) o lo ejecuta.

    Args:
        argv: Argumentos CLI (None = sys.argv[1:]).

    Returns:
        0 si no hubo fallos; 1 si algun proyecto fallo (>= 8).
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Backup DEV-SPACE -> Google Drive")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--dry-run", action="store_true", help="solo audita el plan")
    parser.add_argument(
        "--include-sensitive", action="store_true",
        help="incluye proyectos sensibles (Historia Clinica/JURIDICO/DB caliche)",
    )
    args = parser.parse_args(argv)

    projects = _discover_projects(args.src, include_sensitive=args.include_sensitive)
    plan = _plan_copy(projects, args.dest, DEFAULT_EXCLUDES)
    logger.info("Plan: %d proyectos -> %s", len(plan), args.dest)
    for entry in plan:
        logger.info("  %s -> %s", entry.src.name, entry.dst)
    if args.dry_run:
        logger.info("Dry run: sin copia.")
        return 0
    summary = run_copy(plan)
    logger.info("Resumen: %d OK, %d FAIL de %d", summary.copied, summary.failed, len(plan))
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
