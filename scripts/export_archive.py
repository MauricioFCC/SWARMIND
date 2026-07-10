#!/usr/bin/env python3
"""
export_archive.py — Universal Export & Archive Script

Crea un archivo comprimido del proyecto listo para:
  - Subir a un repositorio alterno en GitHub
  - Archivado offline
  - Distribución

Uso:
    python scripts/export_archive.py                          # Exporta proyecto actual
    python scripts/export_archive.py --project CQE            # Exporta por nombre
    python scripts/export_archive.py --output ../backups/     # Directorio destino
    python scripts/export_archive.py --format zip             # Formato: tar.gz (defecto) o zip
    python scripts/export_archive.py --dry-run                # Solo muestra qué se incluiría

Características:
  - Respeta .gitignore (usa git ls-files si hay repo, sino exclude patterns)
  - Excluye automáticamente: target/, __pycache__, .venv, .git, .env, lancedb data
  - Comprime al máximo (gzip level 9 o ZIP deflate)
  - Genera manifiesto de archivos incluidos
  - Mínimo peso posible sin excluir archivos del proyecto
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Constants — default exclusion patterns (fallback si no hay git)
# ---------------------------------------------------------------------------

EXCLUDE_DIRS: Set[str] = {
    ".git", "__pycache__", ".venv", "venv", "env",
    "target", "node_modules", ".egg-info",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".coverage", "htmlcov", "coverage",
    "exports",  # no exportar exports anteriores
}

EXCLUDE_FILES: Set[str] = {
    ".env", ".env.local", ".envrc",
    "*.pyc", "*.pyo", "*.pyd",
    ".DS_Store", "Thumbs.db", "desktop.ini",
    "*.swp", "*.swo", "*~",
    "*.orig", "*.rej", "*.bak", "*.backup",
    "*.log", "*.profraw",
    "*.tar.gz", "*.zip", "*.7z", "*.rar",
}

EXCLUDE_PATTERNS: List[str] = [
    "harness/db/lancedb/",
    "harness/db/_archived/",
    "harness/db/import/",
    "harness/db/iteration_reports/",
    "99_Hermes_Brain/lancedb_data/",
    "99_Hermes_Brain/logs/",
    "outputs/",
    "logs/",
    "fuzz/corpus/",
    "fuzz/artifacts/",
    "proptest-regressions/",
    ".installed/",
    ".cargo/",
    "bindings/python/legacy/",
    "dist/",
    "build/",
    "*.egg-info/",
]

# Extensiones binarias que se comprimen peor (las añadimos para info)
BINARY_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
    ".mp4", ".avi", ".mov", ".mkv",
    ".mp3", ".wav", ".ogg", ".flac",
    ".ttf", ".otf", ".woff", ".woff2",
    ".pdf", ".dll", ".so", ".dylib", ".exe",
}


def get_git_tracked_files(project_root: Path) -> Optional[List[str]]:
    """Obtiene lista de archivos trackeados por git (incluye no modificados)."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=True, cwd=project_root,
        )
        files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
        # También incluir archivos modificados no staged
        result2 = subprocess.run(
            ["git", "ls-files", "--modified"],
            capture_output=True, text=True, check=True, cwd=project_root,
        )
        modified = [f.strip() for f in result2.stdout.split("\n") if f.strip()]
        return list(set(files + modified))
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def should_exclude(path: str, root: Path) -> bool:
    """Verifica si un path debe ser excluido del archive."""
    rel = Path(path).as_posix()

    # Directorios excluidos
    for part in Path(rel).parts:
        if part in EXCLUDE_DIRS:
            return True

    # Patrones de exclusión
    for pattern in EXCLUDE_PATTERNS:
        if pattern.endswith("/"):
            if rel.startswith(pattern) or f"/{pattern}" in rel:
                return True
        elif pattern in rel:
            return True

    # Extensiones de archivo excluidas
    for ext in EXCLUDE_FILES:
        if ext.startswith("*"):
            if rel.endswith(ext[1:]):
                return True
        elif rel == ext:
            return True

    # .env files
    if rel.endswith(".env") and not rel.endswith(".env.example"):
        return True

    return False


def collect_files(project_root: Path) -> List[Path]:
    """Colecta todos los archivos a incluir en el archive."""
    # Intentar usar git primero (más preciso, respeta .gitignore)
    git_files = get_git_tracked_files(project_root)
    if git_files is not None:
        files = []
        for f in git_files:
            full_path = project_root / f
            if full_path.is_file() and not should_exclude(f, project_root):
                files.append(full_path)
        print(f"  [GIT] Usando git ls-files: {len(files)} archivos trackeados")
        return files

    # Fallback: walk manual
    print("  [WARN] No se detecto repo git. Usando walk manual (puede incluir archivos no deseados)")
    files = []
    for root, dirs, names in os.walk(project_root):
        # Podar dirs excluidos in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        rel_root = Path(root).relative_to(project_root).as_posix()
        if should_exclude(rel_root + "/", project_root):
            dirs[:] = []
            continue
        for name in names:
            rel_path = f"{rel_root}/{name}" if rel_root else name
            if should_exclude(rel_path, project_root):
                continue
            files.append(Path(root) / name)
    return files


def create_tar_gz(project_root: Path, output_path: Path, files: List[Path], verbose: bool = False) -> int:
    """Crea archive tar.gz con compresión máxima."""
    total_bytes = 0
    file_count = 0

    print(f"  [TAR] Creando {output_path.name} ...")
    with tarfile.open(output_path, "w:gz", compresslevel=9) as tar:
        for file_path in sorted(files):
            try:
                arcname = str(file_path.relative_to(project_root)).replace("\\", "/")
                tar.add(file_path, arcname=arcname, recursive=False)
                size = file_path.stat().st_size
                total_bytes += size
                file_count += 1
                if verbose:
                    print(f"     + {arcname} ({_human_size(size)})")
            except Exception as e:
                print(f"     [WARN] Error anadiendo {file_path}: {e}")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [OK] {file_count} archivos, {_human_size(total_bytes)} raw -> {size_mb:.2f} MB comprimido")
    return file_count


def create_zip(project_root: Path, output_path: Path, files: List[Path], verbose: bool = False) -> int:
    """Crea archive ZIP con compresión deflate."""
    total_bytes = 0
    file_count = 0

    print(f"  [ZIP] Creando {output_path.name} ...")
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file_path in sorted(files):
            try:
                arcname = str(file_path.relative_to(project_root)).replace("\\", "/")
                zf.write(file_path, arcname=arcname)
                size = file_path.stat().st_size
                total_bytes += size
                file_count += 1
                if verbose:
                    print(f"     + {arcname} ({_human_size(size)})")
            except Exception as e:
                print(f"     [WARN] Error anadiendo {file_path}: {e}")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [OK] {file_count} archivos, {_human_size(total_bytes)} raw -> {size_mb:.2f} MB comprimido")
    return file_count


def generate_manifest(project_root: Path, files: List[Path], output_path: Path) -> Path:
    """Genera manifiesto de archivos incluidos."""
    manifest_path = output_path.with_suffix(".txt")
    total_size = 0
    by_extension: Dict[str, int] = {}

    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(f"Manifiesto de Exportación\n")
        f.write(f"{'=' * 60}\n")
        f.write(f"Proyecto: {project_root.name}\n")
        f.write(f"Fecha: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"Total archivos: {len(files)}\n")
        f.write(f"{'=' * 60}\n\n")

        for file_path in sorted(files):
            try:
                size = file_path.stat().st_size
                total_size += size
                rel = str(file_path.relative_to(project_root)).replace("\\", "/")
                ext = file_path.suffix.lower()
                by_extension[ext] = by_extension.get(ext, 0) + 1
                f.write(f"{_human_size(size):>8}  {rel}\n")
            except OSError:
                pass

        f.write(f"\n{'=' * 60}\n")
        f.write(f"Total: {len(files)} archivos, {_human_size(total_size)}\n")
        f.write(f"{'=' * 60}\n\n")

        f.write("Archivos por extensión:\n")
        for ext, count in sorted(by_extension.items(), key=lambda x: -x[1]):
            ext_name = ext if ext else "(sin extensión)"
            f.write(f"  {ext_name:>12}: {count}\n")

    print(f"  [MAN] Manifiesto: {manifest_path.name}")
    return manifest_path


def _human_size(size_bytes: int) -> str:
    """Formatea bytes a representación legible."""
    if size_bytes == 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB")
    size = float(size_bytes)
    for unit in units:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def get_project_name(project_root: Path) -> str:
    """Detecta nombre del proyecto desde config."""
    # Intentar Cargo.toml
    cargo = project_root / "Cargo.toml"
    if cargo.exists():
        for line in cargo.read_text().split("\n"):
            if line.strip().startswith("name ="):
                return line.split("=")[1].strip().strip('"')
    # Intentar pyproject.toml
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        for line in pyproject.read_text().split("\n"):
            if line.strip().startswith("name ="):
                return line.split("=")[1].strip().strip('"')
    return project_root.name


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _s(text: str) -> str:
    """Strips non-ASCII characters for Windows console compatibility."""
    return text.encode('ascii', 'ignore').decode('ascii')


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Universal Export & Archive Script — Crea archive comprimido del proyecto",
    )
    parser.add_argument("--project", type=str, default=None,
                        help="Nombre del proyecto (detectado automáticamente)")
    parser.add_argument("--output", type=str, default=None,
                        help="Directorio de salida (defecto: ../exports/ o ./exports/)")
    parser.add_argument("--format", type=str, choices=["tar.gz", "zip"], default="tar.gz",
                        help="Formato de compresión (defecto: tar.gz)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo mostrar qué se incluiría, sin crear archive")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Mostrar cada archivo incluido")
    parser.add_argument("--manifest", action="store_true", default=True,
                        help="Generar manifiesto .txt (defecto: sí)")

    args = parser.parse_args()

    # Detectar raíz del proyecto
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent  # scripts/ → raíz
    project_name = args.project or get_project_name(project_root)

    # Directorio de salida
    output_dir: Path
    if args.output:
        output_dir = Path(args.output).resolve()
    else:
        # Buscar un directorio exports/ compartido entre proyectos
        candidates = [
            project_root / "exports",
            project_root.parent / "exports",
            Path.home() / "Documents" / "DEV-SPACE" / "exports",
        ]
        for c in candidates:
            if c.exists() or c.parent.exists():
                output_dir = c
                break
        else:
            output_dir = project_root / "exports"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ext = args.format
    archive_name = f"{project_name}_{timestamp}.{ext}"
    output_path = output_dir / archive_name

    print(f"\n{'=' * 60}")
    print(f"  [EXPORT] Archive - {project_name}")
    print(f"{'=' * 60}")
    print(f"  [DIR]  Proyecto:  {project_root}")
    print(f"  [OUT]  Salida:    {output_path}")
    print(f"  [FMT]  Formato:   {ext}")
    print(f"  [NAME] Proyecto:  {project_name}")
    print()

    # Colectar archivos
    files = collect_files(project_root)
    if not files:
        print("  [ERROR] No se encontraron archivos para exportar.")
        sys.exit(1)

    raw_size = sum(f.stat().st_size for f in files if f.is_file())
    print(f"  [STATS] {len(files)} archivos, {_human_size(raw_size)} raw")

    if args.dry_run:
        print(f"\n  {'-' * 50}")
        print(f"  DRY RUN - No se creo el archive")
        print(f"  {'-' * 50}")
        if args.verbose:
            for f in sorted(files):
                rel = str(f.relative_to(project_root)).replace("\\", "/")
                print(f"    {rel}")
        return

    # Crear archive
    if ext == "zip":
        count = create_zip(project_root, output_path, files, args.verbose)
    else:
        count = create_tar_gz(project_root, output_path, files, args.verbose)

    # Manifiesto
    if args.manifest:
        generate_manifest(project_root, files, output_path)

    # Resumen final
    compressed_size = output_path.stat().st_size
    ratio = compressed_size / raw_size * 100 if raw_size > 0 else 0
    print(f"\n  {'-' * 50}")
    print(f"  [OK] EXPORTACION COMPLETADA")
    print(f"  {'-' * 50}")
    print(f"  [FILE] {output_path.name}")
    print(f"  [SIZE] {_human_size(raw_size)} -> {_human_size(compressed_size)} ({ratio:.1f}%)")
    print(f"  [MAN]  Manifiesto: {(output_dir / archive_name).with_suffix('.txt').name}")
    print(f"  [DIR]  Directorio: {output_dir}")
    print()


if __name__ == "__main__":
    main()
