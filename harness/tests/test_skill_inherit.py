"""Tests para skill_inherit — herencia ``inherit:`` real y testeable.

Frontera 2026 (Anthropic Agent Skills + progressive disclosure): cada skill
declara ``inherit:`` (rutas relativas a ``.opencode/``) que estaba inerte.
Estos tests fijan: parseo del frontmatter, resolucion de la skill real
``architecture`` (hereda N1+N2), fail-fast ante paths ausentes, rechazo de
path traversal e integridad referencial de TODO el corpus de skills.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from harness.context.skill_composition import SkillCompositionError
from harness.context.skill_inherit import (
    InheritResolution,
    parse_inherit,
    resolve_inherit,
    validate_inherit_corpus,
)

# Raiz del proyecto: harness/tests/test_skill_inherit.py -> SWARMIND/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OPENCODE_DIR = PROJECT_ROOT / ".opencode"
SKILLS_DIR = OPENCODE_DIR / "skills"

#: Rutas que la skill real architecture declara heredar.
ARCHITECTURE_INHERITS = ("core/base_principles.md", "core/fde_principles.md")


@pytest.fixture
def make_skill(tmp_path: Path) -> Callable[..., Path]:
    """Fabrica un SKILL.md de prueba dentro de un corpus temporal.

    Returns:
        Callable ``(frontmatter, name) -> Path`` que escribe el archivo.
    """

    def _make(frontmatter: str, name: str = "demo") -> Path:
        """Escribe ``<tmp>/skills/<name>/SKILL.md`` con el frontmatter dado.

        Args:
            frontmatter: Bloque YAML interno (sin los delimitadores ``---``).
            name: Nombre del directorio de la skill.

        Returns:
            Path del SKILL.md creado.
        """
        skill_dir = tmp_path / "skills" / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(f"---\n{frontmatter}\n---\nbody\n", encoding="utf-8")
        return skill_md

    return _make


def test_parse_inherit_extracts_list(make_skill: Callable[..., Path]) -> None:
    """parse_inherit extrae la lista de rutas declaradas."""
    skill_md = make_skill("name: demo\ninherit:\n  - core/a.md\n  - core/b.md")
    assert parse_inherit(skill_md) == ("core/a.md", "core/b.md")


def test_parse_inherit_without_key_returns_empty(make_skill: Callable[..., Path]) -> None:
    """Una skill sin ``inherit:`` devuelve tupla vacia."""
    skill_md = make_skill("name: demo\ndescription: x")
    assert parse_inherit(skill_md) == ()


def test_parse_inherit_rejects_non_list(make_skill: Callable[..., Path]) -> None:
    """Un ``inherit:`` escalar (no lista) falla con error accionable."""
    skill_md = make_skill("name: demo\ninherit: core/a.md")
    with pytest.raises(SkillCompositionError, match="WHAT"):
        parse_inherit(skill_md)


def test_resolve_inherit_real_skill_architecture() -> None:
    """La skill real architecture resuelve N1+N2 e incluye su contenido."""
    skill_md = SKILLS_DIR / "architecture" / "SKILL.md"
    resolution = resolve_inherit(skill_md, OPENCODE_DIR)

    assert isinstance(resolution, InheritResolution)
    assert resolution.skill_name == "architecture"
    assert resolution.declared == ARCHITECTURE_INHERITS
    assert tuple(rel for rel, _path, _exists in resolution.resolved) == ARCHITECTURE_INHERITS
    assert all(exists for _rel, _path, exists in resolution.resolved)
    assert all(path.is_file() for _rel, path, _exists in resolution.resolved)
    assert "PRINCIPIOS UNIVERSALES" in resolution.content
    assert "FDE" in resolution.content


def test_resolve_inherit_missing_path_raises(
    make_skill: Callable[..., Path], tmp_path: Path
) -> None:
    """Una ruta heredada ausente lanza CompositionError con WHAT."""
    skill_md = make_skill("name: demo\ninherit:\n  - core/no-existe.md")
    with pytest.raises(SkillCompositionError, match="WHAT"):
        resolve_inherit(skill_md, tmp_path)


def test_resolve_inherit_rejects_path_traversal(
    make_skill: Callable[..., Path], tmp_path: Path
) -> None:
    """(Adversarial) una ruta que escapa base_dir se rechaza."""
    skill_md = make_skill("name: demo\ninherit:\n  - ../../etc/passwd")
    with pytest.raises(SkillCompositionError, match="WHAT"):
        resolve_inherit(skill_md, tmp_path)


def test_validate_inherit_corpus_real_all_resolve() -> None:
    """Integridad referencial: TODO el corpus real resuelve sin errores."""
    assert validate_inherit_corpus(SKILLS_DIR, OPENCODE_DIR) == []


def test_validate_inherit_corpus_reports_missing(
    make_skill: Callable[..., Path], tmp_path: Path
) -> None:
    """validate acumula el error de una ruta ausente sin lanzar."""
    make_skill("name: demo\ninherit:\n  - core/no-existe.md")
    errors = validate_inherit_corpus(tmp_path / "skills", tmp_path)
    assert len(errors) == 1
    assert "WHAT" in errors[0]


def test_resolve_inherit_is_idempotent() -> None:
    """Dos llamadas consecutivas devuelven exactamente lo mismo."""
    skill_md = SKILLS_DIR / "architecture" / "SKILL.md"
    first = resolve_inherit(skill_md, OPENCODE_DIR)
    second = resolve_inherit(skill_md, OPENCODE_DIR)
    assert first == second
