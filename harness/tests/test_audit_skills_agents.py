"""Tests TDD del auditor de skills/agentes (``scripts/audit_skills_agents.py``).

Cubre el checklist de ``skill-engineering`` sobre fixtures en ``tmp_path``:
  - skill sano -> PASS.
  - skill sin ``description`` (sin disparador "Usar cuando") -> FAIL.
  - ``description`` que no inicia con "Usar cuando" -> WARN (D002).
  - skill sin anti-trigger ("Alcance:") -> WARN (D003).
  - agregacion de ``status`` (FAIL > WARN > PASS).
  - ``_apply_fix`` idempotente: la segunda ejecucion no cambia el archivo.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import audit_skills_agents

#: Cuerpo minimo con 3 secciones H2, checklist y anti-patrones.
_BODY = (
    "# demo\n"
    "\n"
    "## Checklist\n"
    "- [ ] uno\n"
    "- [ ] dos\n"
    "\n"
    "## Anti-patrones\n"
    "No usar `eval`; prohibido.\n"
    "\n"
    "## Alcance\n"
    "Solo demo.\n"
)
#: Descripcion con disparador y anti-trigger (SDO completo).
_DESC_FULL = "Usar cuando se prueba el auditor. Alcance: solo demo."


def _write_skill(tmp_path: Path, frontmatter: str) -> Path:
    """Escribe un SKILL.md fixture con el frontmatter dado.

    Args:
        tmp_path: Directorio temporal base.
        frontmatter: Bloque YAML interno (sin los delimitadores ``---``).

    Returns:
        Ruta al SKILL.md creado (directorio ``demo`` para respetar FE003).
    """
    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    path = skill_dir / "SKILL.md"
    path.write_text(f"---\n{frontmatter}\n---\n{_BODY}", encoding="utf-8")
    return path


def _codes(result: audit_skills_agents.AuditResult) -> set[str]:
    """Extrae los codigos de los checks no-PASS de un resultado.

    Args:
        result: Resultado de auditoria.

    Returns:
        Conjunto de codigos con WARN o FAIL.
    """
    return {check.code for check in result.issues}


def test_audit_file_skill_sano_es_pass(tmp_path: Path) -> None:
    """Skill completo (frontmatter + contrato) -> status PASS sin hallazgos."""
    path = _write_skill(
        tmp_path,
        "name: demo\n"
        f'description: "{_DESC_FULL}"\n'
        "version: 1.0.0\n"
        "project_agnostic: true\n"
        "license: MIT\n"
        "compatibility: 'Python 3.12+'",
    )

    result = audit_skills_agents._audit_file(path, "skill")

    assert result.status == "PASS"
    assert result.issues == ()


def test_audit_file_sin_description_es_fail(tmp_path: Path) -> None:
    """Skill sin campo 'description' (sin disparador) -> FAIL (FE004)."""
    path = _write_skill(
        tmp_path,
        "name: demo\n"
        "version: 1.0.0\n"
        "project_agnostic: true\n"
        "license: MIT\n"
        "compatibility: 'Python 3.12+'",
    )

    result = audit_skills_agents._audit_file(path, "skill")

    assert result.status == "FAIL"
    assert "FE004" in _codes(result)


def test_audit_file_description_sin_usar_cuando_es_warn(tmp_path: Path) -> None:
    """Skill con description sin 'Usar cuando' -> WARN (D002)."""
    path = _write_skill(
        tmp_path,
        "name: demo\n"
        'description: "Hace cosas. Alcance: solo demo."\n'
        "version: 1.0.0\n"
        "project_agnostic: true\n"
        "license: MIT\n"
        "compatibility: 'Python 3.12+'",
    )

    result = audit_skills_agents._audit_file(path, "skill")

    assert result.status == "WARN"
    assert "D002" in _codes(result)


def test_audit_file_sin_anti_trigger_es_warn(tmp_path: Path) -> None:
    """Skill con description sin anti-trigger -> WARN (D003)."""
    path = _write_skill(
        tmp_path,
        "name: demo\n"
        'description: "Usar cuando se prueba el auditor."\n'
        "version: 1.0.0\n"
        "project_agnostic: true\n"
        "license: MIT\n"
        "compatibility: 'Python 3.12+'",
    )

    result = audit_skills_agents._audit_file(path, "skill")

    assert result.status == "WARN"
    assert "D003" in _codes(result)


def test_status_agrega_al_peor_check() -> None:
    """status agrega FAIL > WARN > PASS; issues lista solo WARN/FAIL."""
    result = audit_skills_agents.AuditResult(
        kind="skill",
        path=Path("demo/SKILL.md"),
        checks=(
            audit_skills_agents.Check("A", "PASS", "ok"),
            audit_skills_agents.Check("B", "WARN", "warn"),
            audit_skills_agents.Check("C", "FAIL", "fail"),
        ),
    )

    assert result.status == "FAIL"
    assert len(result.issues) == 2


def test_apply_fix_es_idempotente(tmp_path: Path) -> None:
    """_apply_fix: 1a ejecucion normaliza; la 2a no cambia el archivo."""
    path = _write_skill(
        tmp_path,
        "name: demo\n" f'description: "{_DESC_FULL}"',
    )

    assert audit_skills_agents._apply_fix(path) is True
    first_pass = path.read_text(encoding="utf-8")
    assert "license: MIT" in first_pass
    assert "version: 1.0.0" in first_pass
    assert "compatibility:" in first_pass

    assert audit_skills_agents._apply_fix(path) is False
    assert path.read_text(encoding="utf-8") == first_pass
