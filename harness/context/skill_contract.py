"""skill_contract.py — Contratos SDD para skills (ADR-0048).

Define el modelo formal de un skill como componente con contrato:
``SKILL.spec.json`` con contract (schemas de entrada/salida),
preconditions/postconditions e invariantes, mas un failing_test
alineado con la "Ley de Hierro" de ADR-0047 (NO SKILL WITHOUT A
FAILING TEST FIRST).

El orchestrator puede validar el contrato antes de componer o
ejecutar un skill, rechazando invocaciones que no cumplan las
precondiciones (specs enforced, no advisory).

Uso:
    contract = load_skill_contract(Path(".opencode/skills/atdd-spec"))
    errors = validate_contract(contract)   # [] si es valido
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
_SPEC_FILENAME = "SKILL.spec.json"
_SPEC_VERSION = "1.0.0"
_MAX_DESCRIPTION_CHARS = 256


@dataclass(frozen=True)
class SkillContract:
    """Contrato formal SDD de un skill (fuente unica de verdad).

    Attributes:
        name: Nombre del skill (coincide con el directorio).
        version: Version semver del contrato.
        description: Descripcion breve del contrato.
        contract: Schemas de entrada (input) y salida (output).
        preconditions: Condiciones que deben cumplirse antes de ejecutar.
        postconditions: Condiciones que deben cumplirse despues de ejecutar.
        failing_test: Ruta del test que debe fallar inicialmente.
        invariants: Propiedades que deben mantenerse durante la ejecucion.
    """

    name: str
    version: str = _SPEC_VERSION
    description: str = ""
    contract: dict[str, object] = field(default_factory=dict)
    preconditions: tuple[str, ...] = ()
    postconditions: tuple[str, ...] = ()
    failing_test: str = ""
    invariants: tuple[str, ...] = ()


def load_skill_contract(skill_dir: Path) -> SkillContract | None:
    """Carga y parsea SKILL.spec.json de un directorio de skill.

    Args:
        skill_dir: Directorio del skill (.opencode/skills/<name>).

    Returns:
        SkillContract si el archivo existe y es JSON valido, None si no
        existe el spec (el skill usa el modelo legacy sin contrato).

    Raises:
        ValueError: Si el JSON es invalido, no es un objeto, o faltan
            campos obligatorios (name, preconditions, postconditions,
            failing_test).
    """
    spec_path = skill_dir / _SPEC_FILENAME
    if not spec_path.exists():
        return None
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"WHAT: SKILL.spec.json no es JSON valido en {spec_path}"
            f"WHY: {exc.msg} en linea {exc.lineno} columna {exc.colno}"
            f"WHERE: load_skill_contract() <- {spec_path}"
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError(
            f"WHAT: SKILL.spec.json debe ser un objeto JSON"
            f"WHY: se recibio {type(raw).__name__}"
            f"WHERE: load_skill_contract() <- {spec_path}"
        )
    required = ("name", "preconditions", "postconditions", "failing_test")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(
            f"WHAT: campos obligatorios ausentes en {spec_path}: {missing}"
            f"WHY: el contrato SDD exige pre/postcondiciones y failing_test"
            f"WHERE: load_skill_contract() <- {spec_path}"
        )
    return SkillContract(
        name=str(raw["name"]),
        version=str(raw.get("version", _SPEC_VERSION)),
        description=str(raw.get("description", "")),
        contract=raw.get("contract", {}) if isinstance(raw.get("contract"), dict) else {},
        preconditions=tuple(str(item) for item in raw["preconditions"]),
        postconditions=tuple(str(item) for item in raw["postconditions"]),
        failing_test=str(raw["failing_test"]),
        invariants=tuple(str(item) for item in raw.get("invariants", ())),
    )


def validate_contract(contract: SkillContract | None, skill_dir: Path) -> list[str]:
    """Valida la estructura de un contrato SDD.

    Args:
        contract: Contrato cargado (None si el skill no tiene spec).
        skill_dir: Directorio del skill (para verificar failing_test).

    Returns:
        Lista de errores (vacia si el contrato es valido o no existe).
    """
    if contract is None:
        return []
    errors: list[str] = []
    if not contract.name:
        errors.append(f"{skill_dir.name}: spec 'name' vacio")
    if len(contract.description) > _MAX_DESCRIPTION_CHARS:
        errors.append(
            f"{skill_dir.name}: spec description excede {_MAX_DESCRIPTION_CHARS} chars"
        )
    if not contract.preconditions:
        errors.append(f"{skill_dir.name}: spec sin preconditions (obligatorias)")
    if not contract.postconditions:
        errors.append(f"{skill_dir.name}: spec sin postconditions (obligatorias)")
    if not contract.failing_test:
        errors.append(f"{skill_dir.name}: spec sin failing_test (Ley de Hierro ADR-0047)")
    else:
        test_path = skill_dir / contract.failing_test
        if not test_path.exists():
            errors.append(
                f"{skill_dir.name}: failing_test {contract.failing_test!r} no existe "
                f"(debe fallar inicialmente, luego el skill lo hace pasar)"
            )
    contract_dict = contract.contract
    if "input" not in contract_dict or "output" not in contract_dict:
        errors.append(
            f"{skill_dir.name}: spec contract debe tener claves 'input' y 'output'"
        )
    return errors