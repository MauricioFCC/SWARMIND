"""Motor de propagación incremental, atómico y content-addressed (un destino).

Reemplaza el copiado masivo ``copytree`` por un plan basado en **manifiesto**
(ruta relativa -> sha256/tamaño/mtime):

1. **Fast path**: si el manifiesto y el destino coinciden en tamaño+mtime, no se
   lee ni se copia el archivo (O(1) por archivo sin tocar bytes).
2. **Content-addressed**: si hay duda, se compara SHA-256; solo se escribe si el
   contenido cambió (idempotente, sin "touch" innecesario).
3. **Atómico**: se copia a un temporal en el destino y se hace ``os.replace``;
   un fallo a mitad nunca deja un archivo truncado.
4. **Paralelo**: las copias (I/O-bound) usan ``ThreadPoolExecutor`` acotado.
5. **Seguro**: rechaza rutas que escapan del destino y no sigue symlinks.

Se usa para propagar el cerebro/motor de SWARMIND **solo** a
``~/.config/opencode`` (config global); los proyectos ya no reciben copias.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

_CHUNK = 1 << 20
_MANIFEST_VERSION = 1


@dataclass
class SyncStats:
    """Contadores de una propagación."""

    scanned: int = 0
    copied: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    failed: int = 0
    bytes_copied: int = 0
    errors: list[str] = field(default_factory=list)

    def merge(self, other: SyncStats) -> None:
        """Suma los contadores de otra propagación."""
        self.scanned += other.scanned
        self.copied += other.copied
        self.updated += other.updated
        self.unchanged += other.unchanged
        self.removed += other.removed
        self.failed += other.failed
        self.bytes_copied += other.bytes_copied
        self.errors.extend(other.errors)

    def as_dict(self) -> dict[str, object]:
        """Vista serializable (para ``--json`` y logs)."""
        return {
            "scanned": self.scanned,
            "copied": self.copied,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "removed": self.removed,
            "failed": self.failed,
            "bytes_copied": self.bytes_copied,
            "errors": list(self.errors),
        }

    @property
    def changed(self) -> int:
        """Archivos escritos o eliminados (para decidir si reiniciar opencode)."""
        return self.copied + self.updated + self.removed


@dataclass(frozen=True)
class _Action:
    """Acción planificada para un archivo."""

    src: Path
    dst: Path
    relative: str
    size: int
    mtime_ns: int
    digest: str
    write: bool
    existed: bool


def digest_file(path: Path) -> str:
    """SHA-256 en streaming (O(bytes), memoria constante)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def label_root(root: Path) -> str:
    """Etiqueta estable (sin rutas personales) para el manifiesto de un root."""
    safe = "".join(char if char.isalnum() else "_" for char in root.name) or "root"
    return safe


def manifest_for(target: Path, label: str | None = None) -> Path:
    """Ruta del manifiesto de un destino (``<target>/.sync/<label>.json``)."""
    return target / ".sync" / f"{label or label_root(target)}.json"


def load_manifest(path: Path) -> dict[str, dict[str, object]]:
    """Carga el manifiesto (vacío si no existe o está corrupto)."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    files = data.get("files", {}) if isinstance(data, dict) else {}
    return files if isinstance(files, dict) else {}


def save_manifest(path: Path, files: dict[str, dict[str, object]]) -> None:
    """Guarda el manifiesto de forma atómica y ordenado."""
    payload = {"version": _MANIFEST_VERSION, "files": dict(sorted(files.items()))}
    _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def is_excluded(relative: str, patterns: Iterable[str]) -> bool:
    """True si la ruta relativa (POSIX) casa con algún patrón de exclusión."""
    parts = relative.split("/")
    for pattern in patterns:
        if "/" in pattern and fnmatch.fnmatch(relative, pattern):
            return True
        if "/" not in pattern and any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
    return False


def _relative_files(root: Path, excludes: tuple[str, ...]) -> list[tuple[str, Path]]:
    """Lista (relativo POSIX, ruta) de archivos regulares, sin symlinks."""
    found: list[tuple[str, Path]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if not is_excluded(relative, excludes):
            found.append((relative, path))
    return found


def _within(root: Path, candidate: Path) -> bool:
    """True si ``candidate`` queda dentro de ``root`` (anti path traversal)."""
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _plan(
    src: Path,
    dst: Path,
    previous: dict[str, dict[str, object]],
    excludes: tuple[str, ...],
) -> tuple[list[_Action], dict[str, dict[str, object]]]:
    """Calcula acciones (escribir o no) usando manifiesto + hashes."""
    actions: list[_Action] = []
    manifest: dict[str, dict[str, object]] = {}
    for relative, source in _relative_files(src, excludes):
        target = dst / relative
        if not _within(dst, target):
            continue
        stat = source.stat()
        entry = previous.get(relative, {})
        fast = (
            entry.get("size") == stat.st_size
            and entry.get("mtime_ns") == stat.st_mtime_ns
            and target.is_file()
            and target.stat().st_size == stat.st_size
            and target.stat().st_mtime_ns == entry.get("dst_mtime_ns")
        )
        if fast:
            digest = str(entry.get("sha256", ""))
            write = False
        else:
            digest = digest_file(source)
            write = not content_matches(target, stat.st_size, digest)
        manifest[relative] = {
            "sha256": digest,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "dst_mtime_ns": stat.st_mtime_ns if write else target.stat().st_mtime_ns,
        }
        actions.append(
            _Action(
                source,
                target,
                relative,
                stat.st_size,
                stat.st_mtime_ns,
                digest,
                write,
                target.is_file(),
            )
        )
    return actions, manifest


def content_matches(target: Path, size: int, digest: str) -> bool:
    """True si ``target`` ya tiene ese tamaño y sha256."""
    if not target.is_file() or target.stat().st_size != size:
        return False
    return digest_file(target) == digest


def _copy_atomic(src: Path, dst: Path) -> None:
    """Copia ``src`` a ``dst`` con temporal + ``os.replace`` (atómico)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    temporary = dst.with_name(f".{dst.name}.tmp-{os.getpid()}")
    try:
        shutil.copy2(src, temporary)
        os.replace(temporary, dst)
    finally:
        temporary.unlink(missing_ok=True)


def _apply(actions: list[_Action], workers: int) -> SyncStats:
    """Ejecuta las acciones de escritura en paralelo (I/O-bound)."""
    stats = SyncStats(scanned=len(actions))
    pending = [action for action in actions if action.write]
    stats.unchanged = len(actions) - len(pending)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_copy_atomic, a.src, a.dst): a for a in pending}
        for future in as_completed(futures):
            action = futures[future]
            try:
                future.result()
            except OSError as exc:
                stats.failed += 1
                stats.errors.append(f"{action.relative}: {exc}")
                continue
            if action.existed:
                stats.updated += 1
            else:
                stats.copied += 1
            stats.bytes_copied += action.size
    return stats


def _atomic_write_text(path: Path, text: str) -> None:
    """Escribe texto con temporal + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def sync_tree(
    src: Path,
    dst: Path,
    *,
    excludes: tuple[str, ...] = (),
    manifest_path: Path | None = None,
    dry_run: bool = False,
    workers: int = 8,
) -> SyncStats:
    """Propaga ``src`` a ``dst`` de forma incremental y atómica.

    Args:
        src: Directorio fuente.
        dst: Directorio destino (bajo el root global).
        excludes: Patrones de exclusión (nombres o rutas POSIX).
        manifest_path: Manifiesto propio del árbol (None = sin fast path).
        dry_run: Si True, planifica sin escribir.
        workers: Copias concurrentes (I/O-bound).

    Returns:
        ``SyncStats`` con los contadores del árbol.
    """
    if not src.is_dir():
        return SyncStats()
    previous = load_manifest(manifest_path) if manifest_path else {}
    actions, manifest = _plan(src, dst, previous, excludes)
    if dry_run:
        stats = SyncStats(scanned=len(actions))
        stats.unchanged = sum(1 for action in actions if not action.write)
        stats.copied = len(actions) - stats.unchanged
        return stats
    dst.mkdir(parents=True, exist_ok=True)
    stats = _apply(actions, workers)
    if manifest_path:
        save_manifest(manifest_path, manifest)
    return stats


def sync_file(src: Path, dst: Path, dry_run: bool = False) -> bool:
    """Copia atómica de un archivo si el contenido cambió.

    Args:
        src: Archivo fuente.
        dst: Archivo destino.
        dry_run: Si True, informa si cambiaría sin escribir.

    Returns:
        True si escribió (o escribiría en dry-run); False si ya era idéntico o
        la fuente no existe.
    """
    if not src.is_file():
        return False
    if (
        dst.is_file()
        and dst.stat().st_size == src.stat().st_size
        and digest_file(dst) == digest_file(src)
    ):
        return False
    if not dry_run:
        _copy_atomic(src, dst)
    return True
