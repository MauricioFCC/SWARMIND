"""test_skill_contract.py — Tests del modelo SDD de contratos (ADR-0048)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.context.skill_contract import (
    SkillContract,
    load_skill_contract,
    validate_contract,
)


@pytest.fixture
def spec_dir(tmp_path: Path) -> Path:
    """Crea un directorio de skill con SKILL.spec.json valido."""
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    spec = {
        "name": "demo-skill",
        "version": "1.0.0",
        "description": "Skill demo con contrato SDD.",
        "contract": {
            "input": {"type": "object", "required": ["query"]},
            "output": {"type": "object", "required": ["answer"]},
        },
        "preconditions": ["La query no es vacia"],
        "postconditions": ["Se devuelve un answer no vacio"],
        "failing_test": "tests/test_demo.py",
    }
    (skill_dir / "SKILL.spec.json").write_text(
        json.dumps(spec), encoding="utf-8"
    )
    test_dir = skill_dir / "tests"
    test_dir.mkdir()
    (test_dir / "test_demo.py").write_text(
        "def test_demo() -> None:\n    assert True\n", encoding="utf-8"
    )
    return skill_dir


def test_load_skill_contract_returns_contract(spec_dir: Path) -> None:
    """Carga un SKILL.spec.json valido y devuelve SkillContract."""
    contract = load_skill_contract(spec_dir)
    assert contract is not None
    assert contract.name == "demo-skill"
    assert contract.preconditions == ("La query no es vacia",)
    assert contract.postconditions == ("Se devuelve un answer no vacio",)
    assert contract.failing_test == "tests/test_demo.py"
    assert contract.contract["input"]["type"] == "object"


def test_load_skill_contract_returns_none_without_spec(tmp_path: Path) -> None:
    """Sin SKILL.spec.json el loader devuelve None (modelo legacy)."""
    assert load_skill_contract(tmp_path) is None


def test_load_skill_contract_invalid_json_raises(tmp_path: Path) -> None:
    """JSON malformado lanza ValueError con WHAT/WHY/WHERE."""
    (tmp_path / "SKILL.spec.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="WHAT:"):
        load_skill_contract(tmp_path)


def test_load_skill_contract_missing_fields_raises(tmp_path: Path) -> None:
    """Faltan campos obligatorios -> ValueError listando los ausentes."""
    (tmp_path / "SKILL.spec.json").write_text(
        json.dumps({"name": "x"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="preconditions"):
        load_skill_contract(tmp_path)


def test_load_skill_contract_non_object_raises(tmp_path: Path) -> None:
    """JSON que no es objeto -> TypeError (regla TRY004, tipo invalido)."""
    (tmp_path / "SKILL.spec.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(TypeError, match="objeto JSON"):
        load_skill_contract(tmp_path)


def test_validate_contract_ok_no_errors(spec_dir: Path) -> None:
    """Contrato valido no produce errores de validacion."""
    contract = load_skill_contract(spec_dir)
    assert contract is not None
    errors = validate_contract(contract, spec_dir)
    assert errors == []


def test_validate_contract_none_returns_empty(tmp_path: Path) -> None:
    """Sin contrato no hay errores (skill legacy valido)."""
    assert validate_contract(None, tmp_path) == []


def test_validate_contract_failing_test_missing(tmp_path: Path) -> None:
    """Failing test inexistente -> error (Ley de Hierro ADR-0047)."""
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    contract = SkillContract(
        name="demo-skill",
        preconditions=("x",),
        postconditions=("y",),
        failing_test="tests/missing_test.py",
    )
    errors = validate_contract(contract, skill_dir)
    assert any("failing_test" in error for error in errors)


def test_validate_contract_missing_preconditions(tmp_path: Path) -> None:
    """Sin preconditions -> error."""
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    contract = SkillContract(
        name="demo-skill",
        preconditions=(),
        postconditions=("y",),
        failing_test="ok.py",
    )
    (skill_dir / "ok.py").write_text("", encoding="utf-8")
    errors = validate_contract(contract, skill_dir)
    assert any("preconditions" in error for error in errors)


def test_validate_contract_contract_keys(tmp_path: Path) -> None:
    """Contract sin input/output -> error."""
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    contract = SkillContract(
        name="demo-skill",
        preconditions=("x",),
        postconditions=("y",),
        failing_test="ok.py",
        contract={"type": "object"},
    )
    (skill_dir / "ok.py").write_text("", encoding="utf-8")
    errors = validate_contract(contract, skill_dir)
    assert any("input" in error and "output" in error for error in errors)


def test_validate_contract_long_description(tmp_path: Path) -> None:
    """Description excesiva -> error de longitud."""
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    contract = SkillContract(
        name="demo-skill",
        description="x" * 300,
        preconditions=("x",),
        postconditions=("y",),
        failing_test="ok.py",
    )
    (skill_dir / "ok.py").write_text("", encoding="utf-8")
    errors = validate_contract(contract, skill_dir)
    assert any("description" in error for error in errors)