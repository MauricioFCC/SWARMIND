"""Contrato de los binarios RuscaDB versionados (clon limpio = memoria nativa).

El repo guarda el C-ABI precompilado por plataforma:

- Windows: ``harness/memory_rag/ruscadb_ffi.dll``
- Linux:   ``harness/memory_rag/libruscadb_ffi.so``

Estos tests garantizan que:

1. el binario de la plataforma actual está versionado,
2. cada binario presente coincide con su sidecar ``.sha256``,
3. el binario carga por el ABI y expone las funciones core.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

_MEMORY_DIR = Path(__file__).resolve().parents[1] / "memory_rag"
BINARIES: dict[str, Path] = {
    "windows": _MEMORY_DIR / "ruscadb_ffi.dll",
    "linux": _MEMORY_DIR / "libruscadb_ffi.so",
}
_PLATFORM = "windows" if sys.platform.startswith("win") else "linux"

#: Extensiones que ``capabilities()`` debe reportar como disponibles.
_CORE_FUNCTIONS = (
    "ruscadb_open_opts",
    "ruscadb_create_index",
    "ruscadb_update_record",
    "ruscadb_delete_record",
    "ruscadb_get_record",
    "ruscadb_integrity_check",
    "ruscadb_backup",
)


def _sha256(path: Path) -> str:
    """SHA-256 hexadecimal del archivo (streaming)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for bloque in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _present() -> list[Path]:
    """Binarios presentes en el checkout."""
    return [path for path in BINARIES.values() if path.is_file()]


class TestBinarioVersionado:
    """El binario precompilado debe viajar con el repo y ser integro."""

    def test_binario_de_la_plataforma_presente(self) -> None:
        """Cada plataforma trae su binario (no un placeholder)."""
        binary = BINARIES[_PLATFORM]
        assert binary.is_file(), f"falta el binario versionado: {binary}"
        assert binary.stat().st_size > 1024 * 1024

    def test_sidecars_presentes(self) -> None:
        """Cada binario presente tiene su sidecar de checksum."""
        for binary in _present():
            checksum = binary.with_name(binary.name + ".sha256")
            assert checksum.is_file(), f"falta {checksum.name}; ejecuta --write"

    def test_checksums_coinciden(self) -> None:
        """Si se recompilo un binario hay que re-fijar su checksum."""
        for binary in _present():
            checksum = binary.with_name(binary.name + ".sha256")
            esperado = checksum.read_text(encoding="utf-8").split()[0].strip()
            assert _sha256(binary) == esperado, (
                f"El binario {binary.name} cambio: ejecuta "
                "`python scripts/pin_ruscadb_binary.py --write`"
            )

    def test_no_estan_ignorados_por_git(self) -> None:
        """Ambos binarios deben poder versionarse (reglas de negación)."""
        ignore = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(
            encoding="utf-8"
        )
        assert "!harness/memory_rag/ruscadb_ffi.dll" in ignore
        assert "!harness/memory_rag/libruscadb_ffi.so" in ignore


@pytest.mark.skipif(not _present(), reason="sin binario RuscaDB en esta plataforma")
class TestCargaDelBinario:
    """El binario cargado por ctypes debe exponer el ABI core."""

    def test_carga_y_capacidades_core(self) -> None:
        """``load_library`` funciona y las funciones core están disponibles."""
        from harness.memory_rag import ruscadb

        ruscadb._LIB = None  # forzar recarga limpia del artefacto versionado
        libreria = ruscadb.load_library()
        assert libreria is not None

        capacidades = ruscadb.capabilities()
        faltantes = [nombre for nombre in _CORE_FUNCTIONS if not capacidades.get(nombre)]
        assert not faltantes, f"ABI incompleto: {faltantes}"
        assert callable(ruscadb.execute)
        assert callable(ruscadb.read_page)
        assert callable(ruscadb.write_page)
