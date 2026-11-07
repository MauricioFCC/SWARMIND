#!/usr/bin/env python3
"""Instalación completa del entorno de desarrollo de SWARMIND (Windows/Linux/macOS).

Equivalente en Python a ``scripts/install.ps1`` para poder ejecutarlo aunque la
política de ejecución de PowerShell bloquee los ``.ps1``:

    python scripts/install.py            # instalación completa
    python scripts/install.py --dry-run  # solo simula

Pasos:
1. Verifica Python >= 3.12 (el propio intérprete que ejecuta este script).
2. Verifica/instala ``uv`` (si falta, ``python -m pip install uv``).
3. Instala dependencias: ``uv sync --extra dev``.
4. Enlaza ``.opencode/{agents,skills,core}`` al global de opencode
   (symlink; si el SO no lo permite, copia como fallback).
5. Configura git hooks (``core.hooksPath = .githooks``).
6. Verifica ``import harness``, ``uv`` y los enlaces.

Seguridad: 0 secretos, operaciones idempotentes y sin borrados destructivos
(los directorios reales se respaldan antes de reemplazarse).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]
BRAIN_DIRS = ("agents", "skills", "core")
MIN_PYTHON = (3, 12)
STEPS = 6


def log_ok(message: str) -> None:
    """Imprime un paso correcto."""
    print(f"  [OK] {message}", flush=True)


def log_warn(message: str) -> None:
    """Imprime un aviso."""
    print(f"  [!]  {message}", flush=True)


def log_info(message: str) -> None:
    """Imprime información de dry-run."""
    print(f"  [i]  {message}", flush=True)


def log_step(number: int, message: str) -> None:
    """Imprime el encabezado de un paso."""
    print(f"\n[{number}/{STEPS}] {message}", flush=True)


def fail(message: str) -> NoReturn:
    """Termina la instalación con un error legible."""
    print("\nINSTALACION FALLIDA:", file=sys.stderr)
    print(f"  {message}", file=sys.stderr)
    print("\n  Revisa los errores arriba.", file=sys.stderr)
    raise SystemExit(1)


def global_dir() -> Path:
    """Directorio global de opencode (``OPENCODE_GLOBAL_DIR`` o ~/.config)."""
    override = os.environ.get("OPENCODE_GLOBAL_DIR")
    return Path(override).expanduser() if override else Path.home() / ".config" / "opencode"


def check_python() -> None:
    """Falla si el intérprete actual es anterior a Python 3.12."""
    version = sys.version_info
    if (version.major, version.minor) < MIN_PYTHON:
        fail(
            f"Python {version.major}.{version.minor} detectado; se requiere >= 3.12 "
            "(descarga: https://www.python.org/downloads/)"
        )
    log_ok(f"Python {version.major}.{version.minor}.{version.micro}")


def ensure_uv(dry_run: bool) -> str | None:
    """Verifica ``uv`` y, si falta, intenta instalarlo con pip.

    Args:
        dry_run: Si es True, solo informa la acción.

    Returns:
        Ruta de ``uv`` en PATH o ``None`` en dry-run sin ``uv``.
    """
    uv = shutil.which("uv")
    if uv:
        log_ok(f"uv ya instalado: {version_of([uv, '--version'])}")
        return uv
    log_warn("uv no encontrado. Instalando via pip...")
    if dry_run:
        log_info("dry-run: python -m pip install uv")
        return None
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "uv", "--quiet"], check=False
    )
    if result.returncode != 0:
        fail("error instalando uv via pip: https://docs.astral.sh/uv/getting-started/installation/")
    uv = shutil.which("uv")
    if uv is None:
        scripts_dir = str(Path(sys.executable).parent)
        os.environ["PATH"] = scripts_dir + os.pathsep + os.environ.get("PATH", "")
        uv = shutil.which("uv")
    if uv is None:
        fail("uv instalado pero no está en PATH; agrega el directorio de scripts de Python")
    log_ok(f"uv instalado: {version_of([uv, '--version'])}")
    return uv


def version_of(command: list[str]) -> str:
    """Devuelve la primera línea de la salida de ``command`` (o vacío)."""
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return (result.stdout or "").strip().splitlines()[0] if result.stdout else ""


def sync_dependencies(uv: str | None, dry_run: bool) -> None:
    """Ejecuta ``uv sync --extra dev`` en la raíz del repo."""
    command = [uv or "uv", "sync", "--extra", "dev"]
    if dry_run:
        log_info(f"dry-run: {' '.join(command)} (cwd={ROOT})")
        return
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        fail(f"uv sync fallo con codigo {result.returncode}")
    log_ok("Dependencias instaladas")


def _backup_existing(dst: Path, dry_run: bool) -> None:
    """Respalda un directorio real antes de reemplazarlo (idempotente)."""
    if not dst.is_dir() or dst.is_symlink():
        return
    backup = dst.with_name(f"{dst.name}.bak.{int(time.time())}")
    log_warn(f"Directorio real existe en {dst} - respaldando a {backup}")
    if not dry_run:
        dst.rename(backup)


def _link_or_copy(src: Path, dst: Path, dry_run: bool) -> None:
    """Crea el symlink; si el SO lo bloquea, copia el directorio (fallback)."""
    if dry_run:
        log_info(f"dry-run: symlink {dst} -> {src} (fallback: copiar)")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and not dst.is_dir():
        dst.unlink()
    try:
        os.symlink(src, dst, target_is_directory=True)
        log_ok(f"Enlazado: {dst.name} -> {src}")
        return
    except OSError as exc:
        log_warn(f"Symlink fallo (Developer Mode deshabilitado?): {exc}")
    log_warn(f"Fallback: copiando {src.name} en lugar de symlink...")
    try:
        shutil.copytree(src, dst)
    except OSError as exc:
        fail(f"No se pudo enlazar ni copiar {src.name}: {exc}")
    log_ok(f"Copiado: {src.name} (fallback sin symlink)")


def link_brain(global_path: Path, dry_run: bool) -> None:
    """Enlaza (o copia) los directorios del cerebro al global de opencode."""
    for name in BRAIN_DIRS:
        src = ROOT / ".opencode" / name
        dst = global_path / name
        if not src.exists():
            log_warn(f"Fuente no existe: {src} - saltando")
            continue
        if dst.is_symlink():
            if dst.resolve() == src.resolve():
                log_ok(f"Symlink {name} ya configurado")
                continue
            log_warn(f"Symlink {name} apunta a {dst.resolve()} - reemplazando")
            if not dry_run:
                dst.unlink()
        _backup_existing(dst, dry_run)
        _link_or_copy(src, dst, dry_run)


def install_hooks(dry_run: bool) -> None:
    """Configura ``core.hooksPath`` si el repo tiene ``.githooks``."""
    if not (ROOT / ".git").exists():
        log_warn("No es un repositorio git - saltando hooks")
        return
    if not (ROOT / ".githooks").exists():
        log_warn("Directorio .githooks no existe - saltando hooks")
        return
    if dry_run:
        log_info("dry-run: git config core.hooksPath .githooks")
        return
    result = subprocess.run(
        ["git", "config", "core.hooksPath", ".githooks"], cwd=ROOT, check=False
    )
    if result.returncode != 0:
        fail("Error configurando git hooks; verifica que .githooks/ exista")
    log_ok("Git hooks configurados (core.hooksPath = .githooks)")


def _import_harness() -> bool:
    """Intenta ``import harness`` (directo y con sys.path explícito)."""
    direct = subprocess.run(
        [sys.executable, "-c", "import harness"], cwd=ROOT, capture_output=True, check=False
    )
    if direct.returncode == 0:
        return True
    code = f"import sys; sys.path.insert(0, r'{ROOT}'); import harness"
    fallback = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, check=False
    )
    return fallback.returncode == 0


def verify(global_path: Path, dry_run: bool) -> None:
    """Verifica import de harness, uv y los enlaces del cerebro."""
    if dry_run:
        log_info("dry-run: se saltaría la verificación de imports")
        return
    if _import_harness():
        log_ok("Import harness exitoso")
    else:
        log_warn("import harness fallo; los hooks y opencode funcionan igualmente")
    uv = shutil.which("uv")
    if uv:
        log_ok(f"uv: {version_of([uv, '--version'])}")
    for name in BRAIN_DIRS:
        dst = global_path / name
        if dst.is_symlink():
            log_ok(f"Symlink {name} activo")
        elif dst.is_dir():
            log_ok(f"Directorio {name} presente (copia)")
        else:
            log_warn(f"{name} no encontrado en {global_path}")


def print_summary() -> None:
    """Imprime los próximos pasos al terminar."""
    print("\n" + "=" * 64)
    print("  INSTALACION COMPLETADA")
    print("=" * 64)
    print("\n  Próximos pasos:")
    print("    .venv/Scripts/Activate.ps1   # Windows (o .venv/bin/activate)")
    print("    python -m harness --help     # Verificar harness")
    print("    git status                   # Verificar hooks")
    print("\n  Si re-instalaste, reinicia opencode para tomar los cambios.\n")


def main(argv: list[str] | None = None) -> int:
    """Ejecuta la instalación completa de SWARMIND."""
    parser = argparse.ArgumentParser(
        description="Instalación del entorno de desarrollo de SWARMIND (sin PowerShell)"
    )
    parser.add_argument("--dry-run", action="store_true", help="simula sin cambios")
    args = parser.parse_args(argv)
    destination = global_dir()
    print("\n" + "=" * 64)
    print("  SWARMIND - Instalación de entorno de desarrollo")
    print("=" * 64)
    print(f"  Root:   {ROOT}")
    print(f"  Global: {destination}")
    print(f"  DryRun: {args.dry_run}")

    log_step(1, "Verificar Python >= 3.12")
    check_python()
    log_step(2, "Verificar/instalar uv (gestor de paquetes)")
    uv = ensure_uv(args.dry_run)
    log_step(3, "Instalar dependencias (uv sync --extra dev)")
    sync_dependencies(uv, args.dry_run)
    log_step(4, "Crear symlinks .opencode -> ~/.config/opencode")
    link_brain(destination, args.dry_run)
    log_step(5, "Instalar git hooks")
    install_hooks(args.dry_run)
    print()
    log_step(6, "Verificación final")
    verify(destination, args.dry_run)
    print_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
