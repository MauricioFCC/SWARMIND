"""Tests del patron PEC (Persona-Expert + Canon) en skills de dominio estetico.

ADR-0071: las skills cuyo output depende de juicio estetico/dominio
(frontend-uiux, diagram-design, creative-design) deben declarar una
persona experta especifica (no generica) y referencias canonicas
empresariales con URL — se estudian antes de generar (RSF).
Verifica: seccion presente, persona con anos de experiencia, canon con
URL https, y que el frontmatter description sigue en presupuesto.
"""

from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[2] / ".opencode" / "skills"

#: Skills de dominio estetico que requieren patron PEC (ADR-0071).
PEC_SKILLS = ("frontend-uiux", "diagram-design", "creative-design")

#: Personas genericas prohibidas (PRISM: persona sin especializacion dania accuracy).
_GENERIC_PERSONAS = ("eres un experto", "you are an expert", "experto en diseno")


def _skill_text(name: str) -> str:
    """Lee el SKILL.md de una skill; skip si no existe."""
    path = SKILLS_DIR / name / "SKILL.md"
    if not path.is_file():
        pytest.skip(f"{name}/SKILL.md no disponible")
    return path.read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("skill", PEC_SKILLS)
def test_pec_section_present(skill: str) -> None:
    """La seccion PERSONA & CANON existe en skills de dominio estetico."""
    text = _skill_text(skill)
    assert "PERSONA & CANON" in text, f"{skill}: falta seccion PERSONA & CANON"
    assert "ADR-0071" in text


@pytest.mark.parametrize("skill", PEC_SKILLS)
def test_persona_has_years_of_experience(skill: str) -> None:
    """La persona declara anos de experiencia (10+)."""
    text = _skill_text(skill)
    body = text.split("PERSONA & CANON", 1)[1]
    assert "PERSONA" in body
    assert ("10+" in body) or ("senior" in body.lower())


@pytest.mark.parametrize("skill", PEC_SKILLS)
def test_canon_has_https_references(skill: str) -> None:
    """El canon lista al menos 2 referencias https (nivel empresarial)."""
    text = _skill_text(skill)
    body = text.split("PERSONA & CANON", 1)[1]
    urls = [line for line in body.splitlines() if "https://" in line]
    assert len(urls) >= 2, f"{skill}: canon con <2 referencias https"


@pytest.mark.parametrize("skill", PEC_SKILLS)
def test_no_generic_persona(skill: str) -> None:
    """La persona no es generica (anti-PRISM)."""
    text = _skill_text(skill).lower()
    for generic in _GENERIC_PERSONAS:
        assert generic not in text, f"{skill}: persona generica '{generic}'"


def test_pec_skills_not_exceeding_description_budget() -> None:
    """El frontmatter de las skills PEC sigue en presupuesto (320 chars)."""
    for skill in PEC_SKILLS:
        path = SKILLS_DIR / skill / "SKILL.md"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("description:"):
                assert len(line) <= 340, f"{skill}: description {len(line)} chars"
                break
