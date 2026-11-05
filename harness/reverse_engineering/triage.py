"""Triaje de artefactos: huella, tipo y estructura sin ejecutar el objetivo.

Primera operación de toda investigación (``core_target_triage``): identifica
qué es un archivo por sus bytes (ELF, PE/.NET, Mach-O, APK/JAR/ZIP, WASM, pyc,
SQLite, firmware, capturas, imágenes...), calcula su SHA-256 y, para archivos
comprimidos, inventaría entradas **sin extraerlas** (la extracción es Deep-only).

Complejidad: O(bytes) para el hash + O(k) para listar k entradas; nunca se
descomprime ni se ejecuta el artefacto.
"""

from __future__ import annotations

import platform
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .evidence import Authority, Confidence, Environment, Evidence, Location, Subject
from .policy import Mode
from .target_router import route

_HEAD_BYTES = 1 << 20
_ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06")
_MACHO_MAGICS = (
    b"\xcf\xfa\xed\xfe",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xfe\xed\xfa\xce",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
)


@dataclass
class ArtifactInfo:
    """Resultado del triaje de un artefacto."""

    kind: str
    size: int
    sha256: str
    confidence: Confidence = Confidence.OBSERVED
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializa el resultado para evidencia/JSON."""
        return {
            "kind": self.kind,
            "size": self.size,
            "sha256": self.sha256,
            "confidence": self.confidence.value,
            "details": self.details,
        }


def _hash_and_head(path: Path) -> tuple[str, int, bytes]:
    """Calcula SHA-256 y tamaño en streaming y devuelve la cabecera."""
    import hashlib

    digest = hashlib.sha256()
    size = 0
    head = b""
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
            if len(head) < _HEAD_BYTES:
                head += chunk[: _HEAD_BYTES - len(head)]
    return digest.hexdigest(), size, head


def _pe_kind(head: bytes) -> tuple[str, dict[str, Any]]:
    """Distingue PE nativo de .NET buscando el metadata CLR (BSJB)."""
    if len(head) > 0x40 and head[0x3C:0x40] and b"PE\x00\x00" in head[0x80:0x200]:
        assembly = head.find(b"BSJB")
        if assembly >= 0:
            return "dotnet", {"clr_metadata_offset": assembly}
        return "pe", {}
    return "pe", {"warning": "cabecera PE no confirmada"}


def _zip_kind(path: Path) -> tuple[str, dict[str, Any]]:
    """Clasifica ZIP por contenido: APK, JAR, Office o ZIP genérico."""
    names: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = [info.filename for info in archive.infolist()[:200]]
    except (zipfile.BadZipFile, OSError) as exc:
        return "zip", {"error": str(exc)}
    if "AndroidManifest.xml" in names:
        return "apk", {"entries": len(names)}
    if any(name.startswith("META-INF/") for name in names):
        return "jar", {"entries": len(names)}
    if any(name.startswith("word/") for name in names):
        return "docx", {"entries": len(names)}
    if any(name.startswith("xl/") for name in names):
        return "xlsx", {"entries": len(names)}
    return "zip", {"entries": len(names)}


_SIMPLE_MAGICS: tuple[tuple[bytes, str], ...] = (
    (b"\x7fELF", "elf"),
    (b"\x00asm", "wasm"),
    (b"SQLite format 3\x00", "sqlite"),
    (b"%PDF-", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF8", "gif"),
    (b"\x1f\x8b", "gzip"),
    (b"\xfd7zXZ\x00", "xz"),
    (b"\x28\xb5\x2f\xfd", "zstd"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"Rar!\x1a\x07", "rar"),
)


def _simple_kind(head: bytes) -> tuple[str, dict[str, Any]] | None:
    """Tipo por magic table (ELF/WASM/SQLite/imágenes/compresión)."""
    for magic, kind in _SIMPLE_MAGICS:
        if head.startswith(magic):
            details = {"bits": 64 if head[4:5] == b"\x02" else 32} if kind == "elf" else {}
            return kind, details
    if len(head) > 262 and head[257:262] == b"ustar":
        return "tar", {}
    if _is_python_bytecode(head):
        return "python-bytecode", {}
    return None


def _is_python_bytecode(head: bytes) -> bool:
    """True si la cabecera empieza con el magic del intérprete actual."""
    import importlib.util

    magic = getattr(importlib.util, "MAGIC_NUMBER", b"")
    return bool(magic) and head.startswith(magic)


def _detect(path: Path, head: bytes) -> tuple[str, dict[str, Any]]:
    """Detecta el tipo por magic bytes y estructura mínima."""
    if head.startswith(b"MZ"):
        return _pe_kind(head)
    if head.startswith(_MACHO_MAGICS):
        return "macho", {}
    if head.startswith(_ZIP_MAGICS):
        return _zip_kind(path)
    simple = _simple_kind(head)
    if simple is not None:
        return simple
    if head and _looks_textual(head):
        return "text", {}
    return "unknown", {}


def _looks_textual(head: bytes) -> bool:
    """Heurística: >90% de bytes UTF-8 imprimibles en la cabecera."""
    try:
        sample = head.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not sample:
        return False
    printable = sum(1 for char in sample if char.isprintable() or char in "\n\r\t")
    return printable / len(sample) > 0.9


def fingerprint(path: Path) -> ArtifactInfo:
    """Identifica un artefacto por sus bytes y calcula su SHA-256.

    Args:
        path: Ruta del archivo a inspeccionar.

    Returns:
        ``ArtifactInfo`` con tipo, tamaño, digest y detalles.

    Raises:
        FileNotFoundError: Si la ruta no es un archivo legible.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"WHAT: no existe el artefacto {path} WHY: ruta inválida WHERE: triage.fingerprint"
        )
    digest, size, head = _hash_and_head(path)
    kind, details = _detect(path, head)
    return ArtifactInfo(
        kind=kind,
        size=size,
        sha256=digest,
        details={**details, "rea_route": _route_details(path, head)},
    )


def _route_details(path: Path, head: bytes) -> dict[str, Any]:
    """Decisión del router REA existente (IDP) para el artefacto."""
    decision = route(str(path), authorized=True, sample=head)
    return {
        "target_type": decision.target_type,
        "method": decision.method,
        "provider": decision.provider,
        "evidence": list(decision.evidence),
        "confidence": decision.confidence,
        "why": decision.why,
    }


def inventory_archive(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    """Lista entradas de un ZIP/TAR sin extraerlas.

    Args:
        path: Archivo comprimido.
        limit: Máximo de entradas a listar (anti zip-bomb de metadatos).

    Returns:
        Lista de ``{"name", "size"}``.

    Raises:
        ValueError: Si el archivo no es ZIP ni TAR.
    """
    entries: list[dict[str, Any]] = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            entries.extend(
                {"name": info.filename, "size": info.file_size}
                for info in archive.infolist()[:limit]
            )
        return entries
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            entries.extend(
                {"name": member.name, "size": member.size}
                for member in archive.getmembers()[:limit]
            )
        return entries
    raise ValueError(
        f"WHAT: {path} no es un ZIP ni TAR WHY: inventario solo para archivos soportados "
        f"WHERE: triage.inventory_archive"
    )


def triage_evidence(path: Path, mode: Mode = Mode.CLEAN_ROOM) -> Evidence:
    """Construye la evidencia ``core_target_triage`` de un artefacto."""
    info = fingerprint(path)
    host = f"{platform.system().lower()}-{platform.machine().lower()}"
    return Evidence(
        subject=Subject(kind=info.kind, sha256=info.sha256, name=path.name),
        operation="core_target_triage",
        params={"path": str(path)},
        result=info.to_dict(),
        summary=f"{info.kind} de {info.size} bytes (sha256 {info.sha256[:12]}...)",
        confidence=info.confidence,
        authority=Authority.ORIGINAL_FILES,
        environment=Environment(
            clean_room=mode is Mode.CLEAN_ROOM,
            engine="builtin",
            host=host,
        ),
        locations=[Location("path", str(path))],
    ).seal()
