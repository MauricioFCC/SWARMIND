"""
Tests TDD para diagram-design scripts/self_check.py — modo --json (ADR-0047).

Cubre la salida JSON parseable del self-check de diagram-design:
  - --json emite {status, files:[{file, status, errors}]}
  - exit code 0 si todo OK, 1 si algun archivo falla
  - modo texto plano (default) sigue funcionando
  - archivo inexistente -> FAIL con error
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Ruta del script self_check.py del skill diagram-design
_SELF_CHECK = (
    Path(__file__).resolve().parents[2] / ".opencode" / "skills" / "diagram-design" / "scripts" / "self_check.py"
)
_ASSETS = _SELF_CHECK.parents[1] / "assets"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Ejecuta self_check.py con argumentos y captura stdout/stderr."""
    return subprocess.run(
        [sys.executable, str(_SELF_CHECK), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


# ===========================================================================
# Modo --json
# ===========================================================================


def test_json_output_estructura() -> None:
    """--json sobre un archivo valido -> {status: OK, files:[...]}."""
    example = _ASSETS / "example-architecture.html"
    if not example.is_file():
        import pytest

        pytest.skip("assets del skill no disponibles")

    result = _run("--json", str(example))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"
    assert len(payload["files"]) == 1
    entry = payload["files"][0]
    assert set(entry) == {"file", "status", "errors"}
    assert entry["status"] == "OK"
    assert entry["errors"] == []


def test_json_archivo_inexistente_fail() -> None:
    """--json sobre archivo inexistente -> status FAIL con error listado."""
    result = _run("--json", str(Path("no-existe-archivo.html")))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "FAIL"
    assert payload["files"][0]["status"] == "FAIL"
    assert len(payload["files"][0]["errors"]) >= 1


def test_json_varios_archivos() -> None:
    """--json con 2 archivos validos -> 2 entries, ambos OK."""
    arch = _ASSETS / "example-architecture.html"
    flow = _ASSETS / "example-data-flow.html"
    if not (arch.is_file() and flow.is_file()):
        import pytest

        pytest.skip("assets del skill no disponibles")

    result = _run("--json", str(arch), str(flow))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert len(payload["files"]) == 2
    assert all(entry["status"] == "OK" for entry in payload["files"])


# ===========================================================================
# Modo texto (default, no romper compatibilidad)
# ===========================================================================


def test_modo_texto_ok() -> None:
    """Sin --json -> linea 'OK <path>' en stdout (formato anterior)."""
    example = _ASSETS / "example-architecture.html"
    if not example.is_file():
        import pytest

        pytest.skip("assets del skill no disponibles")

    result = _run(str(example))

    assert result.returncode == 0
    assert f"OK {example}" in result.stdout


def test_modo_texto_fail() -> None:
    """Sin --json y archivo inexistente -> linea 'FAIL <path>' y exit 1."""
    result = _run("no-existe-archivo.html")

    assert result.returncode == 1
    assert "FAIL" in result.stdout


# ===========================================================================
# Self-check de todos los assets del skill (integracion)
# ===========================================================================


def test_todos_los_assets_del_skill_validos() -> None:
    """Todos los ejemplo-*.html del skill pasan el self-check (calidad del skill)."""
    if not _ASSETS.is_dir():
        import pytest

        pytest.skip("assets del skill no disponibles")

    examples = sorted(_ASSETS.glob("example-*.html"))
    assert len(examples) >= 20, f"esperados >=20 ejemplos, hay {len(examples)}"

    # Ejecutar en batch (los assets validos -> exit 0)
    result = _run("--json", *[str(p) for p in examples])

    assert result.returncode == 0, result.stdout[:500]
    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"
    assert len(payload["files"]) == len(examples)
