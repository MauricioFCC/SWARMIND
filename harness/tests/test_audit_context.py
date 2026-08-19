"""test_audit_context.py — Tests de la auditoria de contexto (ADR-0048)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.audit_context import (
    _has_spec,
    _lines,
    _skill_tokens,
    audit_skills,
)


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    """Crea un directorio de skills de prueba."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    return skills_dir


def _make_skill(skills_dir: Path, name: str, content: str, with_spec: bool = False) -> Path:
    """Crea un skill de prueba con SKILL.md y opcional spec."""
    skill_dir = skills_dir / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    if with_spec:
        (skill_dir / "SKILL.spec.json").write_text(
            '{"name": "' + name + '", "preconditions": ["x"], '
            '"postconditions": ["y"], "failing_test": "t.py"}',
            encoding="utf-8",
        )
    return skill_dir


def test_skill_tokens_counts_estimate(skills_dir: Path) -> None:
    """Estima tokens del SKILL.md via SSOT (minimo 1)."""
    _make_skill(skills_dir, "tiny", "# Tiny\n\nhola mundo")
    assert _skill_tokens(skills_dir / "tiny") >= 1


def test_skill_tokens_zero_without_md(skills_dir: Path) -> None:
    """Sin SKILL.md devuelve 0."""
    (skills_dir / "empty").mkdir()
    assert _skill_tokens(skills_dir / "empty") == 0


def test_has_spec_detects_spec(skills_dir: Path) -> None:
    """Detecta presencia de SKILL.spec.json."""
    _make_skill(skills_dir, "with-spec", "# A", with_spec=True)
    _make_skill(skills_dir, "without-spec", "# B")
    assert _has_spec(skills_dir / "with-spec") is True
    assert _has_spec(skills_dir / "without-spec") is False


def test_lines_counts_md_lines(skills_dir: Path) -> None:
    """Cuenta lineas del SKILL.md."""
    _make_skill(skills_dir, "multi", "# Titulo\nlinea 2\nlinea 3")
    assert _lines(skills_dir / "multi") == 3


def test_audit_skills_report_structure(skills_dir: Path) -> None:
    """El reporte incluye skills, totales y caps."""
    _make_skill(skills_dir, "alpha", "# Alpha\n\ncontenido breve")
    report = audit_skills(skills_dir)
    assert report["inventory_tokens"] >= 1
    assert report["session_tokens"] >= 1
    assert report["cap_per_skill"] == 5000
    assert report["cap_stack"] == 25000
    assert report["stack_over_cap"] is False
    assert report["violations"] == []
    names = [item["name"] for item in report["skills"]]
    assert "alpha" in names


def test_audit_skills_session_capped_by_stack(skills_dir: Path) -> None:
    """El stack inyectado por sesion nunca excede el cap de 25000."""
    for idx in range(10):
        _make_skill(skills_dir, f"skill-{idx}", "# S\n\n" + "palabra token token\n" * 600)
    report = audit_skills(skills_dir)
    assert report["stack_over_cap"] is True
    assert report["session_tokens"] == 25000
    assert report["violations"] == []


def test_audit_skills_marks_zombi(skills_dir: Path) -> None:
    """Skill grande sin spec y sin failing_test -> zombi."""
    _make_skill(skills_dir, "big-legacy", "# Big\n\n" + "linea de texto repetida\n" * 600)
    report = audit_skills(skills_dir)
    skill = next(item for item in report["skills"] if item["name"] == "big-legacy")
    assert skill["zombi"] is True
    assert skill["suggest_split"] is True


def test_audit_skills_marks_over_cap(skills_dir: Path) -> None:
    """Skill sobre 5000 tokens -> violation."""
    _make_skill(skills_dir, "monster", "# Monster\n\n" + "palabra token token\n" * 2000)
    report = audit_skills(skills_dir)
    assert "monster" in report["violations"]
    skill = next(item for item in report["skills"] if item["name"] == "monster")
    assert skill["over_cap"] is True


def test_audit_skills_empty_dir(skills_dir: Path) -> None:
    """Directorio sin skills -> cero tokens, sin violaciones."""
    report = audit_skills(skills_dir)
    assert report["inventory_tokens"] == 0
    assert report["session_tokens"] == 0
    assert report["violations"] == []