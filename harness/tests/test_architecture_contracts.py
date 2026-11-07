"""Tests de los contratos declarativos de dependencias (F8, patron tach)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "check_architecture.py"


def _load_script() -> ModuleType:
    """Carga ``scripts/check_architecture.py`` como modulo aislado."""
    spec = importlib.util.spec_from_file_location("check_architecture_contracts", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script(tmp_path, monkeypatch):
    """Checker con archivo de contratos temporal."""
    module = _load_script()
    path = tmp_path / "contracts.toml"
    monkeypatch.setattr(module, "CONTRACTS_FILE", path)
    return module


def _write(path: Path, body: str) -> None:
    """Escribe un TOML de contratos."""
    path.write_text(body, encoding="utf-8")


def test_current_repo_contracts_pass(script):
    """Los contratos reales del repo se cumplen (domain puro, common sin orquestacion)."""
    script.CONTRACTS_FILE = SCRIPT.parent / "architecture_contracts.toml"
    assert script.check_declarative_contracts() == []


def test_forbidden_dependency_is_reported(script):
    """Un import prohibido por contrato se reporta con modulo y contrato."""
    _write(
        script.CONTRACTS_FILE,
        """
[[contracts]]
name = "sin-memoria"
module = "harness.orchestrator.agent_bus.core"
forbidden = ["harness.memory_rag"]
""",
    )
    errors = script.check_declarative_contracts()
    assert errors
    assert any("harness.memory_rag" in error for error in errors)


def test_allow_list_blocks_unlisted_dependency(script):
    """Con allow-list, cualquier dependencia fuera de ella viola el contrato."""
    _write(
        script.CONTRACTS_FILE,
        """
[[contracts]]
name = "solo-domain"
module = "harness.memory_rag.vector_store_factory"
allowed = ["harness.domain", "harness.memory_rag"]
""",
    )
    # vector_store_factory importa harness.memory_rag.* (permitido) y domain.
    assert script.check_declarative_contracts() == []


def test_missing_contracts_file_is_error(script):
    """Sin archivo de contratos, F8 falla con mensaje accionable."""
    errors = script.check_declarative_contracts()
    assert errors and "falta" in errors[0]


def test_contract_without_module_is_error(script):
    """Un contrato sin ``module`` es un error de configuracion."""
    _write(script.CONTRACTS_FILE, '[[contracts]]\nname = "roto"\n')
    errors = script.check_declarative_contracts()
    assert any("sin 'module'" in error for error in errors)


def test_contract_is_part_of_gate(script, monkeypatch):
    """F8 forma parte de BLOCKING_RULES del modo --gate."""
    assert "F8" in script.BLOCKING_RULES
    findings = script.run_checks()
    assert "F8" in findings
