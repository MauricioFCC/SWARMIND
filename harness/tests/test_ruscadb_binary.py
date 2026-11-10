"""Contrato del binario RuscaDB versionado (clon limpio = memoria nativa lista).

El repo guarda ``harness/memory_rag/ruscadb_ffi.dll`` para que un clon limpio
funcione sin el repo Rust ni cargo. Estos tests garantizan que:

1. el binario sigue versionado (no lo borra un ``git clean`` mal hecho),
2. su checksum coincide con ``ruscadb_ffi.dll.sha256``,
3. carga por el ABI y expone las funciones core (solo Windows).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

_MEMORY_DIR = Path(__file__).resolve().parents[1] / "memory_rag"
BINARY = _MEMORY_DIR / "ruscadb_ffi.dll"
CHECKSUM = _MEMORY_DIR / "ruscadb_ffi.dll.sha256"

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


class TestBinarioVersionado:
    """El binario precompilado debe viajar con el repo y ser integro."""

    def test_binario_presente(self) -> None:
        """El DLL existe y tiene tamano de binario real (no un placeholder)."""
        assert BINARY.is_file(), f"falta el binario versionado: {BINARY}"
        assert BINARY.stat().st_size > 1024 * 1024

    def test_sidecar_de_checksum_presente(self) -> None:
        """Existe el sidecar con el SHA-256 fijado."""
        assert CHECKSUM.is_file(), f"falta {CHECKSUM.name}; ejecuta --write"

    def test_checksum_coincide(self) -> None:
        """Si se recompilo el motor hay que re-fijar el checksum con el script."""
        esperado = CHECKSUM.read_text(encoding="utf-8").split()[0].strip()
        assert _sha256(BINARY) == esperado, (
            "El DLL cambio: ejecuta `python scripts/pin_ruscadb_binary.py --write`"
        )

    def test_no_esta_ignorado_por_git(self) -> None:
        """El binario debe poder versionarse (regla de negacion en .gitignore)."""
        ignore = Path(__file__).resolve().parents[2] / ".gitignore"
        assert "!harness/memory_rag/ruscadb_ffi.dll" in ignore.read_text(encoding="utf-8")


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="DLL solo Windows")
class TestCargaDelBinario:
    """El binario cargado por ctypes debe exponer el ABI core."""

    def test_carga_y_capacidades_core(self) -> None:
        """`load_library` funciona y las funciones core estan disponibles."""
        from harness.memory_rag import ruscadb

        ruscadb._LIB = None  # forzar recarga limpia del artefacto versionado
        libreria = ruscadb.load_library()
        assert libreria is not None

        capacidades = ruscadb.capabilities()
        faltantes = [nombre for nombre in _CORE_FUNCTIONS if not capacidades.get(nombre)]
        assert not faltantes, f"ABI incompleto: {faltantes}"
        # Las operaciones base del C-ABI se exponen como wrappers del modulo.
        assert callable(ruscadb.execute)
        assert callable(ruscadb.read_page)
        assert callable(ruscadb.write_page)
