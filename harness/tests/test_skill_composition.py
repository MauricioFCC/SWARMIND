"""Tests para skill_composition — skills como primitivas (ADR-0075).

Frontera (Pocock v1.0, -63% tokens; Wang set-compatibility): las skills
declaran `calls:` (skills que delegan, resueltas lazy con dedup y deteccion
de ciclos) y `invocation:` (user|model|skill — el tier decide quien puede
invocarla y si un composite tasa la sesion raiz). La poda de conflictos
(set-compatibility) descarta pares contradictorios antes de inyectar.
"""

from pathlib import Path

import pytest

from harness.context.skill_composition import (
    SkillCompositionError,
    parse_calls,
    parse_invocation,
    prune_conflicts,
    resolve_composition,
)


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    """3 skills de prueba: tdd llama a codebase-design y domain-modeling."""
    base = tmp_path / "skills"
    for name, body in {
        "tdd": "---\nname: tdd\ninvocation: user\ncalls: [codebase-design, domain-modeling]\n---\nTDD body",
        "codebase-design": "---\nname: codebase-design\ninvocation: skill\n---\nDesign vocabulary",
        "domain-modeling": "---\nname: domain-modeling\ninvocation: skill\ncalls: [codebase-design]\n---\nGlossary",
        "ask-matt": "---\nname: ask-matt\ninvocation: user\n---\nUser router",
        "grilling": "---\nname: grilling\ninvocation: model\n---\nModel loop",
    }.items():
        d = base / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8")
    return base


def test_parse_calls_from_frontmatter(skills_dir: Path) -> None:
    """parse_calls extrae la lista de skills delegadas."""
    assert parse_calls(skills_dir / "tdd" / "SKILL.md") == (
        "codebase-design",
        "domain-modeling",
    )
    assert parse_calls(skills_dir / "ask-matt" / "SKILL.md") == ()


def test_parse_invocation_tier(skills_dir: Path) -> None:
    """parse_invocation lee el tier (default model)."""
    assert parse_invocation(skills_dir / "tdd" / "SKILL.md") == "user"
    assert parse_invocation(skills_dir / "grilling" / "SKILL.md") == "model"
    assert parse_invocation(skills_dir / "codebase-design" / "SKILL.md") == "skill"


def test_resolve_composition_lazy_dedup(skills_dir: Path) -> None:
    """Resolucion lazy con dedup: tdd no inyecta domain-modeling 2 veces."""
    resolved = resolve_composition("tdd", skills_dir)
    assert resolved.roots == ("tdd",)
    assert resolved.invoked == ("codebase-design", "domain-modeling")
    assert len(resolved.invoked) == len(set(resolved.invoked))


def test_resolve_composition_detects_cycle(tmp_path: Path) -> None:
    """Un ciclo a->b->a falla con error accionable (sin colgarse)."""
    base = tmp_path / "skills"
    for name, calls in (("a", "[b]"), ("b", "[a]")):
        d = base / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {name}\ncalls: {calls}\n---\nx", encoding="utf-8")
    with pytest.raises(SkillCompositionError, match="ciclo"):
        resolve_composition("a", base)


def test_resolve_missing_skill_raises(skills_dir: Path) -> None:
    """La raiz valida resuelve; una skill inexistente falla accionable."""
    ok = resolve_composition("tdd", skills_dir)
    assert ok.roots == ("tdd",)
    with pytest.raises(SkillCompositionError, match="WHAT"):
        resolve_composition("no-existe", skills_dir)


def test_prune_conflicts_removes_contradictions() -> None:
    """Poda de pares conflictivos (set-compatibility de Wang)."""
    selected = ["frontend-uiux", "rust-lang", "quant-trading"]
    out = prune_conflicts(selected)
    assert "frontend-uiux" in out
    assert out == [s for s in selected if s in out]


def test_prune_conflicts_custom_matrix() -> None:
    """Matriz custom: el par conflictivo se poda conservando el orden."""
    out = prune_conflicts(
        ["a", "b", "c"],
        conflicts=frozenset({frozenset({"a", "b"})}),
    )
    assert out == ["a", "c"]
