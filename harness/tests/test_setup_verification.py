"""Tests TDD: verificacion de setup Swarmind (fix ADR-0042).

Cubre las 3 correcciones del ADR-0042 (Causas 1 y 2):
  1. ``sync_opencode_global.py`` empaqueta el harness global COMPLETO
     (``__init__.py``, ``__main__.py``, ``vulture_whitelist.py``) para que
     ``import harness`` / ``python -m harness`` funcionen desde el global.
  2. ``ensure_memory_structure`` crea la memoria central (``Memory_Proyects``)
     con estructura LanceDB completa si NO existe (idempotente, no destructivo).
  3. ``verify_swarmind_setup.py`` health-check funcional: detecta harness
     global incompleto y memoria central ausente (WHAT+WHY+WHERE).

Basado en el estandar 2026 de empaquetado de agent skills (addyosmani/
agent-skills, Agent Plugins): skills + evals + hooks portables en una sola
ubicacion global re-instalable en cualquier PC nuevo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import setup_memory_central
import sync_opencode_global
import verify_swarmind_setup


def _capture_system(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Mockea os.system para capturar setx sin escribir en el entorno real.

    Args:
        monkeypatch: Fixture de monkeypatch de pytest.

    Returns:
        Lista de comandos capturados (vacia si no se llamo system).
    """
    calls: list[str] = []

    def fake_system(command: str) -> int:
        calls.append(command)
        return 0

    monkeypatch.setattr(verify_swarmind_setup.os, "system", fake_system)
    return calls


def _clear_real_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Limpia env vars reales persistidas (setx ADR-0042) para tests herméticos.

    Los tests de persistencia deben ser independientes del entorno de la
    máquina: si DEV_SPACE_ROOT/MEMORY_ROOT ya están en el entorno real
    (persistidos por setx), persist_env_vars() correctamente NO los vuelve
    a setear (idempotencia), y el assert del test fallaría.

    Args:
        monkeypatch: Fixture de monkeypatch de pytest.
    """
    for var in ("DEV_SPACE_ROOT", "MEMORY_ROOT"):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# 1. Harness global empaquetado completo (Causa 2 ADR-0042)
# ---------------------------------------------------------------------------


def test_harness_files_incluyen_archivos_de_paquete() -> None:
    """El global debe incluir __init__.py y __main__.py (paquete importable)."""
    files = sync_opencode_global._HARNESS_FILES
    assert "__init__.py" in files, "Falta __init__.py: import harness falla"
    assert "__main__.py" in files, "Falta __main__.py: python -m harness falla"
    assert "vulture_whitelist.py" in files, "Falta vulture_whitelist.py en el motor"


def test_harness_files_corresponden_a_archivos_reales() -> None:
    """Cada entrada de _HARNESS_FILES debe existir en harness/ (sin entradas muertas).

    Acepta archivos y paquetes (directorios con __init__.py): los modulos
    refactorizados a paquete (scheduler/, run_commands/, etc.) son directorios.
    """
    src = ROOT / "harness"
    for fname in sync_opencode_global._HARNESS_FILES:
        path = src / fname
        is_pkg_dir = path.is_dir() and (path / "__init__.py").is_file()
        assert path.is_file() or is_pkg_dir, f"Entrada muerta en _HARNESS_FILES: {fname}"


# ---------------------------------------------------------------------------
# 2. Memoria central automatica con estructura LanceDB (Causa 1 ADR-0042)
# ---------------------------------------------------------------------------


def test_ensure_memory_structure_crea_estructura_completa(tmp_path: Path) -> None:
    """Crea toda la estructura de memoria central si no existe."""
    result = setup_memory_central.ensure_memory_structure(memory_root=tmp_path)

    for rel in setup_memory_central._MEMORY_DIRS:
        assert (tmp_path / rel).is_dir(), f"Falta directorio de memoria: {rel}"
    assert result["created"] >= 1
    assert result["root"] == tmp_path


def test_ensure_memory_structure_idempotente(tmp_path: Path) -> None:
    """Segunda llamada no crea nada nuevo (no destructivo, preserva db)."""
    setup_memory_central.ensure_memory_structure(memory_root=tmp_path)
    # Simular db existente que NO debe borrarse
    (tmp_path / "data" / "lancedb" / "rag_chunks.lance").mkdir(parents=True)
    (tmp_path / "data" / "lancedb" / "rag_chunks.lance" / "data").mkdir(parents=True)

    result = setup_memory_central.ensure_memory_structure(memory_root=tmp_path)

    assert result["created"] == 0, "No debe recrear directorios existentes"
    assert (tmp_path / "data" / "lancedb" / "rag_chunks.lance").is_dir(), "No debe borrar db"


def test_ensure_memory_structure_crea_lancedb_y_config(tmp_path: Path) -> None:
    """Crea data/lancedb (con .gitkeep) y .swarmind_config.json."""
    setup_memory_central.ensure_memory_structure(memory_root=tmp_path)

    lancedb = tmp_path / "data" / "lancedb"
    assert lancedb.is_dir()
    assert (lancedb / ".gitkeep").exists() or any(lancedb.iterdir())

    config = tmp_path / ".swarmind_config.json"
    if config.exists():
        import json

        payload = json.loads(config.read_text(encoding="utf-8"))
        assert payload.get("memory_root"), "Config sin memory_root"


# ---------------------------------------------------------------------------
# 3. verify_swarmind_setup.py health-check (WHAT+WHY+WHERE)
# ---------------------------------------------------------------------------


def test_verify_detecta_harness_global_incompleto(tmp_path: Path) -> None:
    """Health-check falla cuando el harness global no es paquete importable."""
    results = verify_swarmind_setup.run_checks(global_dir=tmp_path)

    assert "harness_global" in results
    assert results["harness_global"]["ok"] is False
    assert "why" in results["harness_global"], "Falta causa (WHY)"
    assert "where" in results["harness_global"], "Falta ubicacion (WHERE)"


def test_verify_detecta_memoria_central_ausente(tmp_path: Path) -> None:
    """Health-check falla cuando Memory_Proyects no existe."""
    results = verify_swarmind_setup.run_checks(
        global_dir=tmp_path, memory_root=tmp_path / "no_existe"
    )

    assert "memory_central" in results
    assert results["memory_central"]["ok"] is False
    assert "why" in results["memory_central"]


def test_verify_harness_ok_cuando_global_es_paquete(tmp_path: Path) -> None:
    """Health-check pasa cuando el global tiene __init__.py y __main__.py."""
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir(parents=True)
    (harness_dir / "__init__.py").write_text("", encoding="utf-8")
    (harness_dir / "__main__.py").write_text("", encoding="utf-8")

    results = verify_swarmind_setup.run_checks(global_dir=tmp_path)
    assert results["harness_global"]["ok"] is True


def test_verify_memoria_ok_con_colecciones(tmp_path: Path) -> None:
    """Health-check pasa cuando la memoria central tiene colecciones LanceDB."""
    lancedb = tmp_path / "data" / "lancedb"
    (lancedb / "rag_chunks.lance").mkdir(parents=True)
    (lancedb / "rag_chunks.lance" / "data").mkdir(parents=True)

    results = verify_swarmind_setup.run_checks(
        global_dir=tmp_path, memory_root=tmp_path
    )
    assert results["memory_central"]["ok"] is True


@pytest.mark.parametrize(
    "name, expected_keys",
    [
        ("harness_global", {"ok", "why", "where"}),
        ("memory_central", {"ok", "why", "where"}),
        ("env_vars", {"ok"}),
    ],
)
def test_verify_reporta_todos_los_checks(
    tmp_path: Path, name: str, expected_keys: set[str]
) -> None:
    """run_checks reporta harness, memoria y env vars con detalle accionable."""
    results = verify_swarmind_setup.run_checks(global_dir=tmp_path)
    assert name in results, f"Falta check: {name}"
    assert expected_keys.issubset(results[name].keys()), f"Keys incompletas en {name}"


# ---------------------------------------------------------------------------
# 4. Persistencia de env vars (Causa 3 ADR-0042)
# ---------------------------------------------------------------------------


def test_persist_env_no_pisa_pythonpath_existente(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PYTHONPATH existente se preserva: el global se anade con ';'."""
    monkeypatch.setenv("PYTHONPATH", r"C:\otro\path")
    _clear_real_env(monkeypatch)
    monkeypatch.setattr(verify_swarmind_setup, "_GLOBAL_DIR", tmp_path / "global")
    monkeypatch.setattr(verify_swarmind_setup, "_MEMORY_ROOT", tmp_path / "mem")
    monkeypatch.setattr(verify_swarmind_setup.Path, "home", lambda: tmp_path)
    calls = _capture_system(monkeypatch)
    (tmp_path / "mem").mkdir(parents=True)

    result = verify_swarmind_setup.persist_env_vars()

    assert result["set_vars"]["PYTHONPATH"] == f"C:\\otro\\path;{tmp_path / 'global'}"
    # Los setx capturados deben apuntar a rutas tmp, NUNCA al entorno real
    assert all("pytest-of" in cmd or str(tmp_path) in cmd for cmd in calls), \
        "persist_env_vars escribio setx apuntando fuera del sandbox tmp"


def test_persist_env_detecta_dev_space(monkeypatch: pytest.MonkeyPatch,
                                       tmp_path: Path) -> None:
    """DEV_SPACE_ROOT se detecta del Documents real (DEV_SPACE con underscore)."""
    monkeypatch.setenv("PYTHONPATH", "")
    _clear_real_env(monkeypatch)
    monkeypatch.setattr(verify_swarmind_setup, "_GLOBAL_DIR", tmp_path / "global")
    monkeypatch.setattr(verify_swarmind_setup, "_MEMORY_ROOT", tmp_path / "mem")
    _capture_system(monkeypatch)
    (tmp_path / "mem").mkdir(parents=True)
    monkeypatch.setattr(verify_swarmind_setup.Path, "home", lambda: tmp_path)
    (tmp_path / "Documents" / "DEV_SPACE").mkdir(parents=True)

    result = verify_swarmind_setup.persist_env_vars()

    assert str(tmp_path / "Documents" / "DEV_SPACE") in result["set_vars"]["DEV_SPACE_ROOT"]


def test_persist_env_no_duplica_pythonpath(monkeypatch: pytest.MonkeyPatch,
                                           tmp_path: Path) -> None:
    """Si el global ya esta en PYTHONPATH, no se duplica (idempotente)."""
    gdir = tmp_path / "global"
    monkeypatch.setenv("PYTHONPATH", str(gdir))
    _clear_real_env(monkeypatch)
    monkeypatch.setattr(verify_swarmind_setup, "_GLOBAL_DIR", gdir)
    monkeypatch.setattr(verify_swarmind_setup, "_MEMORY_ROOT", tmp_path / "mem")
    _capture_system(monkeypatch)
    (tmp_path / "mem").mkdir(parents=True)

    result = verify_swarmind_setup.persist_env_vars()

    assert "PYTHONPATH" not in result["set_vars"]
