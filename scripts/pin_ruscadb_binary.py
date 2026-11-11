"""Fija/verifica el checksum SHA-256 de los binarios RuscaDB versionados.

El repositorio guarda los binarios precompilados del C-ABI para que un clon
limpio funcione sin toolchain Rust:

- Windows: ``harness/memory_rag/ruscadb_ffi.dll``
- Linux:   ``harness/memory_rag/libruscadb_ffi.so``

Este script opera sobre los binarios **presentes** (o sobre uno con
``--binary``):

- ``--write``   regenera el sidecar ``<binario>.sha256`` tras recompilar.
- ``--check``   verifica que el binario coincide con su sidecar (default).

Uso:
    python scripts/pin_ruscadb_binary.py            # verificar presentes
    python scripts/pin_ruscadb_binary.py --write    # re-fijar presentes
    python scripts/pin_ruscadb_binary.py --binary linux --write
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINARIES: dict[str, Path] = {
    "windows": ROOT / "harness" / "memory_rag" / "ruscadb_ffi.dll",
    "linux": ROOT / "harness" / "memory_rag" / "libruscadb_ffi.so",
}


def sidecar(binary: Path) -> Path:
    """Ruta del sidecar de checksum de un binario.

    Args:
        binary: Ruta del binario.

    Returns:
        ``<binario>.sha256``.
    """
    return binary.with_name(binary.name + ".sha256")


def sha256_of(path: Path) -> str:
    """Devuelve el SHA-256 hexadecimal del archivo.

    Args:
        path: Archivo a hashear.

    Returns:
        Digest SHA-256 en hexadecimal.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for bloque in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _targets(platform: str | None) -> list[Path]:
    """Binarios objetivo: uno concreto o todos los presentes."""
    if platform is not None:
        return [BINARIES[platform]]
    return [path for path in BINARIES.values() if path.is_file()]


def write_checksum(platform: str | None = None) -> int:
    """Escribe el checksum de cada binario objetivo; devuelve exit code."""
    targets = _targets(platform)
    if not targets:
        print("ERROR: no hay binarios RuscaDB presentes")
        return 1
    for binary in targets:
        if not binary.is_file():
            print(f"ERROR: no existe {binary}")
            return 1
        digest = sha256_of(binary)
        sidecar(binary).write_text(f"{digest}  {binary.name}\n", encoding="utf-8")
        print(f"OK: {sidecar(binary).name} = {digest}")
    return 0


def check_checksum(platform: str | None = None) -> int:
    """Compara cada binario objetivo con su sidecar; exit 0 si coinciden."""
    targets = _targets(platform)
    if not targets:
        print("ERROR: no hay binarios RuscaDB presentes")
        return 1
    for binary in targets:
        if not binary.is_file():
            print(f"ERROR: no existe {binary}")
            return 1
        checksum = sidecar(binary)
        if not checksum.is_file():
            print(f"ERROR: no existe {checksum}; ejecuta --write")
            return 1
        esperado = checksum.read_text(encoding="utf-8").split()[0].strip()
        actual = sha256_of(binary)
        if actual != esperado:
            print(
                f"ERROR: checksum no coincide para {binary.name}\n"
                f"  esperado={esperado}\n  actual  ={actual}"
            )
            return 1
        print(f"OK: {binary.name} ({binary.stat().st_size} bytes) sha256={actual}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada CLI.

    Args:
        argv: Argumentos (default: ``sys.argv[1:]``).

    Returns:
        Exit code del proceso.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Regenerar el checksum")
    parser.add_argument(
        "--binary", choices=sorted(BINARIES), default=None,
        help="Limitar a un binario (default: todos los presentes)",
    )
    args = parser.parse_args(argv)
    return (
        write_checksum(args.binary) if args.write else check_checksum(args.binary)
    )


if __name__ == "__main__":
    sys.exit(main())
