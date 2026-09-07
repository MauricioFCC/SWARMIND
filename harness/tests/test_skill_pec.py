"""Tests del patron PEC universal (persona-experta + canon) en TODAS las skills.

ADR-0072: PEC es la esencia aplicable a cualquier skill — persona experta
rica (rol senior + anos + especializacion) y canon de referencias frontera
por especialidad con URL, envebido en cada SKILL.md. Verifica: seccion en
todas las skills, persona con anos/senior, canon con >=2 https, sin persona
generica (anti-PRISM) y descriptions en presupuesto.
"""

from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[2] / ".opencode" / "skills"

#: Personas genericas prohibidas (PRISM: persona sin especializacion dania accuracy).
_GENERIC_PERSONAS = ("eres un experto", "you are an expert")


def _all_skill_dirs() -> list[Path]:
    """Lista los directorios de skills disponibles."""
    return sorted(d for d in SKILLS_DIR.iterdir() if d.is_dir())


@pytest.mark.parametrize("skill_dir", _all_skill_dirs(), ids=lambda p: p.name)
def test_pec_section_present_everywhere(skill_dir: Path) -> None:
    """TODAS las skills tienen la seccion PERSONA & CANON (PEC universal)."""
    path = skill_dir / "SKILL.md"
    if not path.is_file():
        pytest.skip(f"{skill_dir.name}: SKILL.md ausente")
    text = path.read_text(encoding="utf-8-sig")
    assert "PERSONA & CANON" in text, f"{skill_dir.name}: falta seccion PEC"


@pytest.mark.parametrize("skill_dir", _all_skill_dirs(), ids=lambda p: p.name)
def test_persona_has_seniority(skill_dir: Path) -> None:
    """La persona declara seniority (10+ anos o 'senior')."""
    path = skill_dir / "SKILL.md"
    if not path.is_file():
        pytest.skip(f"{skill_dir.name}: SKILL.md ausente")
    body = path.read_text(encoding="utf-8-sig").split("PERSONA & CANON", 1)[1]
    assert ("10+" in body) or ("15+" in body) or ("12+" in body) or ("senior" in body.lower())


@pytest.mark.parametrize("skill_dir", _all_skill_dirs(), ids=lambda p: p.name)
def test_canon_has_https_references(skill_dir: Path) -> None:
    """El canon lista >=2 referencias https (nivel frontera/empresarial)."""
    path = skill_dir / "SKILL.md"
    if not path.is_file():
        pytest.skip(f"{skill_dir.name}: SKILL.md ausente")
    body = path.read_text(encoding="utf-8-sig").split("PERSONA & CANON", 1)[1]
    urls = [line for line in body.splitlines() if "https://" in line]
    assert len(urls) >= 2, f"{skill_dir.name}: canon con <2 referencias https"


@pytest.mark.parametrize("skill_dir", _all_skill_dirs(), ids=lambda p: p.name)
def test_no_generic_persona(skill_dir: Path) -> None:
    """La persona no es generica (anti-PRISM, ADR-0072)."""
    path = skill_dir / "SKILL.md"
    if not path.is_file():
        pytest.skip(f"{skill_dir.name}: SKILL.md ausente")
    text = path.read_text(encoding="utf-8-sig").lower()
    for generic in _GENERIC_PERSONAS:
        assert generic not in text, f"{skill_dir.name}: persona generica '{generic}'"


@pytest.mark.parametrize("skill_dir", _all_skill_dirs(), ids=lambda p: p.name)
def test_anti_hedging_present(skill_dir: Path) -> None:
    """Cada skill declara su regla ANTI-HEDGING (tradeoff expertise/clarity)."""
    path = skill_dir / "SKILL.md"
    if not path.is_file():
        pytest.skip(f"{skill_dir.name}: SKILL.md ausente")
    body = path.read_text(encoding="utf-8-sig").split("PERSONA & CANON", 1)[1]
    assert "ANTI-HEDGING" in body, f"{skill_dir.name}: falta ANTI-HEDGING"


def test_descriptions_still_in_budget() -> None:
    """Las descriptions del frontmatter siguen en presupuesto (<=340 chars)."""
    violations: list[str] = []
    for skill_dir in _all_skill_dirs():
        path = skill_dir / "SKILL.md"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("description:"):
                if len(line) > 340:
                    violations.append(f"{skill_dir.name}: {len(line)} chars")
                break
    assert not violations, f"descriptions fuera de presupuesto: {violations}"
