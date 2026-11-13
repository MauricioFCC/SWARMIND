"""Tests de la migración de frontmatter de skills a ``metadata``.

Contratos (spec ``skills-metadata-migration.md``):
  AC1/AC2: mueve ``domain``/``version``/``project_agnostic`` a ``metadata``
  como strings y elimina los top-level.
  AC3/AC4: preserva ``inherit``/``variables``/``invocation``/``calls`` y el body.
  AC5: idempotente (segunda pasada sin cambios).
  AC6: el validador acepta layout legacy y migrado.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from harness.context.skills_metadata import migrate_frontmatter, migrate_skills

LEGACY = """---
name: demo
domain: education
description: "Usar cuando el usuario quiere aprender."
license: MIT
compatibility: 'Python 3.12+'
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
variables:
  - LEARNER_TYPE: adult
metadata:
  author: demo-skill
---
# Demo

## Reglas

- Una cosa.
"""


def _front(text: str) -> str:
    """Devuelve el bloque de frontmatter (sin delimitadores)."""
    return text.split("---", 2)[1]


class TestMigrateFrontmatter:
    def test_mueve_los_tres_campos_a_metadata(self) -> None:
        """AC1/AC2: top-level fuera; metadata con strings."""
        migrado, changed = migrate_frontmatter(LEGACY)

        assert changed is True
        front = _front(migrado)
        assert "\ndomain:" not in front
        assert "\nversion:" not in front
        assert "\nproject_agnostic:" not in front
        assert '  domain: "education"' in front
        assert '  version: "1.0.0"' in front
        assert '  project_agnostic: "true"' in front

    def test_preserva_extensiones_y_body(self) -> None:
        """AC3/AC4: inherit/variables/calls intactos y body byte-idéntico."""
        migrado, _ = migrate_frontmatter(LEGACY)

        assert "inherit:\n  - core/base_principles.md" in migrado
        assert "variables:\n  - LEARNER_TYPE: adult" in migrado
        assert migrado.endswith("# Demo\n\n## Reglas\n\n- Una cosa.\n")

    def test_idempotente(self) -> None:
        """AC5: segunda pasada no cambia nada."""
        migrado, _ = migrate_frontmatter(LEGACY)
        otra, changed = migrate_frontmatter(migrado)

        assert changed is False
        assert otra == migrado

    def test_sin_metadata_crea_bloque(self) -> None:
        """Sin metadata existente, se crea al final del frontmatter."""
        sin_meta = LEGACY.replace("metadata:\n  author: demo-skill\n", "")
        migrado, _ = migrate_frontmatter(sin_meta)

        assert "metadata:\n" in migrado
        assert '  domain: "education"' in migrado

    def test_sin_campos_no_cambia(self) -> None:
        """Un frontmatter ya limpio no se toca."""
        limpio = "---\nname: demo\ndescription: Usar cuando x.\n---\n# Body\n"
        migrado, changed = migrate_frontmatter(limpio)

        assert changed is False
        assert migrado == limpio

    def test_sin_frontmatter_no_cambia(self) -> None:
        """Un archivo sin frontmatter se devuelve igual."""
        texto = "# Solo body\n"
        assert migrate_frontmatter(texto) == (texto, False)

    def test_project_agnostic_false_se_cita(self) -> None:
        """El booleano se serializa como string 'false'."""
        legacy = LEGACY.replace("project_agnostic: true", "project_agnostic: false")
        migrado, _ = migrate_frontmatter(legacy)

        assert '  project_agnostic: "false"' in migrado

    def test_preserva_invocation_y_calls(self) -> None:
        """Las extensiones de composición no se tocan."""
        legacy = LEGACY.replace(
            "inherit:\n", "invocation: user\ncalls: [a, b]\ninherit:\n"
        )
        migrado, _ = migrate_frontmatter(legacy)

        assert "invocation: user" in migrado
        assert "calls: [a, b]" in migrado


class TestPropertyBased:
    @given(
        domain=st.from_regex(r"[a-z]{2,12}", fullmatch=True),
        version=st.from_regex(r"[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}", fullmatch=True),
        body=st.text(min_size=1, max_size=80).filter(lambda t: "---" not in t),
    )
    def test_idempotencia_y_body(self, domain: str, version: str, body: str) -> None:
        """PBT: migrar dos veces es estable y no toca el body."""
        legacy = (
            f"---\nname: demo\ndomain: {domain}\nversion: {version}\n"
            f"project_agnostic: true\ndescription: Usar cuando x.\n---\n{body}\n"
        )
        una, _ = migrate_frontmatter(legacy)
        dos, changed = migrate_frontmatter(una)

        assert changed is False
        assert dos == una
        assert dos.endswith(body + "\n")


class TestMigrateSkills:
    def test_recorre_skill_md_y_min(self, tmp_path: Path) -> None:
        """Migra ambos archivos y reporta el conteo."""
        skill = tmp_path / "demo"
        skill.mkdir()
        (skill / "SKILL.md").write_text(LEGACY, encoding="utf-8")
        (skill / "SKILL.min.md").write_text(LEGACY, encoding="utf-8")

        report = migrate_skills(tmp_path, write=True)

        assert report.updated == 2
        for name in ("SKILL.md", "SKILL.min.md"):
            texto = (skill / name).read_text(encoding="utf-8")
            assert '  domain: "education"' in texto
        segundo = migrate_skills(tmp_path, write=True)
        assert segundo.updated == 0


def test_validador_dual_read_metadata(tmp_path: Path) -> None:
    """AC6: el validador lee version/project desde metadata."""
    from scripts.validate_skills import _parse_frontmatter

    migrado, _ = migrate_frontmatter(LEGACY)
    campos, error = _parse_frontmatter(migrado)

    assert error is None
    assert campos["metadata"]["version"] == "1.0.0"
    assert campos["metadata"]["project_agnostic"] == "true"
