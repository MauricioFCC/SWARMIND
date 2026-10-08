"""
Tests de la herencia `inherit:` cableada en AgentDispatcher.

Cubre: inyeccion OFF por defecto, inyeccion ON por env, override explicito,
skill sin herencia, ruta heredada rota (best-effort) y metadatos en el dict
devuelto por `find_skill_for_task`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from harness.evolve_loop.skill_generator import SkillGenerator
from harness.orchestrator.agent_dispatcher import (
    ENV_INHERIT_INJECT,
    AgentDispatcher,
    _inherit_inject_enabled,
    _resolve_inherit_meta,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

#: Raiz del repo (para resolver .opencode/ sin depender del CWD).
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Skill real con `inherit:` declarado en su frontmatter.
_ARCH_SKILL = str(_REPO_ROOT / ".opencode" / "skills" / "architecture" / "SKILL.md")

#: Rutas declaradas por la skill architecture (orden de frontmatter).
_ARCH_DECLARED = ("core/base_principles.md", "core/fde_principles.md")

#: Marcador presente en `.opencode/core/base_principles.md`.
_BASE_MARKER = "PRINCIPIOS UNIVERSALES"

#: Marcador que separa skill y herencia.
_SEPARATOR_MARKER = "SWARMIND:SKILL-INHERIT-BEGIN"


@pytest.fixture(autouse=True)
def _clear_skill_cache():
    """Limpia el @lru_cache de `_read_skill_md` antes y despues de cada test."""
    AgentDispatcher._read_skill_md.cache_clear()
    yield
    AgentDispatcher._read_skill_md.cache_clear()


# ---------------------------------------------------------------------------
# _inherit_inject_enabled
# ---------------------------------------------------------------------------


class TestInheritInjectEnabled:
    """Tests del parseo de la variable de entorno."""

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " On "])
    def test_truthy_values_enable(self, monkeypatch, value):
        """Los valores afirmativos deben habilitar la inyeccion."""
        monkeypatch.setenv(ENV_INHERIT_INJECT, value)
        assert _inherit_inject_enabled() is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
    def test_other_values_disable(self, monkeypatch, value):
        """Cualquier otro valor (o ausencia) mantiene la inyeccion OFF."""
        monkeypatch.setenv(ENV_INHERIT_INJECT, value)
        assert _inherit_inject_enabled() is False


# ---------------------------------------------------------------------------
# _read_skill_md + herencia
# ---------------------------------------------------------------------------


class TestReadSkillMdInherit:
    """Tests de `_read_skill_md` con resolucion de `inherit:`."""

    def test_default_env_off_does_not_inject(self, monkeypatch):
        """Con la env OFF, no debe anexar el contenido heredado."""
        monkeypatch.delenv(ENV_INHERIT_INJECT, raising=False)

        content = AgentDispatcher._read_skill_md(_ARCH_SKILL)

        assert _BASE_MARKER not in content
        assert _SEPARATOR_MARKER not in content

    def test_meta_default_env_off_reports_declared(self, monkeypatch):
        """Los metadatos deben exponer las rutas declaradas aunque no se inyecten."""
        monkeypatch.delenv(ENV_INHERIT_INJECT, raising=False)

        declared, ok = _resolve_inherit_meta(_ARCH_SKILL)

        assert declared == _ARCH_DECLARED
        assert ok is True

    def test_env_on_injects_inheritance(self, monkeypatch):
        """Con la env ON, debe anexar el contenido heredado con marcador."""
        monkeypatch.setenv(ENV_INHERIT_INJECT, "1")

        content = AgentDispatcher._read_skill_md(_ARCH_SKILL)

        assert _SEPARATOR_MARKER in content
        assert _BASE_MARKER in content

    def test_include_inherit_true_overrides_env_off(self, monkeypatch):
        """`include_inherit=True` debe inyectar aunque la env este OFF."""
        monkeypatch.delenv(ENV_INHERIT_INJECT, raising=False)

        content = AgentDispatcher._read_skill_md(_ARCH_SKILL, include_inherit=True)

        assert _BASE_MARKER in content

    def test_include_inherit_false_overrides_env_on(self, monkeypatch):
        """`include_inherit=False` debe suprimir la inyeccion aunque la env este ON."""
        monkeypatch.setenv(ENV_INHERIT_INJECT, "1")

        content = AgentDispatcher._read_skill_md(_ARCH_SKILL, include_inherit=False)

        assert _BASE_MARKER not in content

    def test_skill_without_inherit_appends_nothing(self, tmp_path: Path):
        """Una skill sin `inherit:` no debe anexar nada y reportar `()`."""
        skill = tmp_path / "plain" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("# Plain Skill\n\nSin herencia.", encoding="utf-8")

        content = AgentDispatcher._read_skill_md(str(skill), include_inherit=True)
        declared, ok = _resolve_inherit_meta(str(skill))

        assert content == "# Plain Skill\n\nSin herencia."
        assert declared == ()
        assert ok is True

    def test_broken_inherit_path_degrades(self, tmp_path: Path):
        """Una ruta heredada inexistente no debe lanzar: degrada al skill."""
        skill = tmp_path / "broken" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        raw = (
            "---\nname: broken\ninherit:\n  - core/nonexistent-xyz.md\n---\n"
            "# Broken Skill\n"
        )
        skill.write_text(raw, encoding="utf-8")

        content = AgentDispatcher._read_skill_md(str(skill), include_inherit=True)
        declared, ok = _resolve_inherit_meta(str(skill))

        assert content == raw  # sin separador de herencia anexado
        assert declared == ("core/nonexistent-xyz.md",)
        assert ok is False


# ---------------------------------------------------------------------------
# find_skill_for_task — metadatos
# ---------------------------------------------------------------------------


class TestFindSkillForTaskInheritMeta:
    """Tests de los metadatos `inherited`/`inherited_ok` en el dict de skill."""

    def test_reports_declared_paths(self, monkeypatch):
        """Debe exponer las rutas declaradas resueltas y `inherited_ok`."""
        fake_skill: dict[str, Any] = {"name": "architecture", "path": _ARCH_SKILL}
        monkeypatch.setattr(
            SkillGenerator, "find_in_registry", lambda _query: dict(fake_skill)
        )
        monkeypatch.delenv(ENV_INHERIT_INJECT, raising=False)

        result = AgentDispatcher().find_skill_for_task("arquitectura del sistema")

        assert result is not None
        assert result["inherited"] == _ARCH_DECLARED
        assert result["inherited_ok"] is True

    def test_broken_path_reports_not_ok(self, monkeypatch, tmp_path: Path):
        """Con una ruta rota, debe reportar `inherited_ok=False` sin lanzar."""
        skill = tmp_path / "broken2" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        raw = "---\nname: broken2\ninherit:\n  - core/missing-abc.md\n---\n# B\n"
        skill.write_text(raw, encoding="utf-8")
        fake_skill: dict[str, Any] = {"name": "broken2", "path": str(skill)}
        monkeypatch.setattr(
            SkillGenerator, "find_in_registry", lambda _query: dict(fake_skill)
        )

        result = AgentDispatcher().find_skill_for_task("tarea rara")

        assert result is not None
        assert result["inherited"] == ("core/missing-abc.md",)
        assert result["inherited_ok"] is False
        assert result["content"] == raw
