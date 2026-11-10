"""Fija/verifica el checksum SHA-256 del binario RuscaDB versionado.

El repositorio guarda ``harness/memory_rag/ruscadb_ffi.dll`` (compilado con
``cargo build -p ruscadb-ffi``) para que un clon limpio funcione de inmediato,
sin el repo Rust ni toolchain. Este script:

- ``--write``   regenera ``ruscadb_ffi.dll.sha256`` tras recompilar el motor.
- ``--check``   verifica que el binario coincide con el checksum (default).

Uso:
    python scripts/pin_ruscadb_binary.py            # verificar
    python scripts/pin_ruscadb_binary.py --write    # re-fijar checksum
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

BINARY = Path(__file__).resolve().parents[1] / "harness" / "memory_rag" / "ruscadb_ffi.dll"
CHECKSUM = BINARY.with_suffix(BINARY.suffix + ".sha256")


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


def write_checksum() -> int:
    """Escribe el checksum actual en el sidecar y devuelve exit code."""
    if not BINARY.is_file():
        print(f"ERROR: no existe {BINARY}")
        return 1
    digest = sha256_of(BINARY)
    CHECKSUM.write_text(f"{digest}  {BINARY.name}\n", encoding="utf-8")
    print(f"OK: {CHECKSUM.name} = {digest}")
    return 0


def check_checksum() -> int:
    """Compara binario y sidecar; devuelve exit code (0 = coincide)."""
    if not BINARY.is_file():
        print(f"ERROR: no existe {BINARY}")
        return 1
    if not CHECKSUM.is_file():
        print(f"ERROR: no existe {CHECKSUM}; ejecuta --write")
        return 1
    esperado = CHECKSUM.read_text(encoding="utf-8").split()[0].strip()
    actual = sha256_of(BINARY)
    if actual != esperado:
        print(f"ERROR: checksum no coincide\n  esperado={esperado}\n  actual  ={actual}")
        return 1
    print(f"OK: {BINARY.name} ({BINARY.stat().st_size} bytes) sha256={actual}")
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
    args = parser.parse_args(argv)
    return write_checksum() if args.write else check_checksum()


if __name__ == "__main__":
    sys.exit(main())
