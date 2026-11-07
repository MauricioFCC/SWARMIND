"""Contrato del ciclo frontera: las superficies de uso constante deben existir.

Doctrina: el meta-prompt de ciclo (load → research → design → spec/SDD → TDD
adversarial → docs) se dispara con la petición explícita del usuario. Para que
eso no dependa de la memoria del agente, las tres superficies (skill, comando y
sección de `AGENTS.md`) son contrato ejecutable: si alguien borra una fase o
elimina el atajo `/frontera`, este test falla.

Archivos verificados:
  - .opencode/skills/frontier-engineering/{SKILL.md,SKILL.min.md}
  - .opencode/commands/frontera.md
  - AGENTS.md (sección "Ciclo Frontera")
  - .opencode/config/project_config.yaml (SKILLS.total / skill_list)
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_DIR = ROOT / ".opencode" / "skills" / "frontier-engineering"
COMMAND = ROOT / ".opencode" / "commands" / "frontera.md"
AGENTS_MD = ROOT / "AGENTS.md"
PROJECT_CONFIG = ROOT / ".opencode" / "config" / "project_config.yaml"

#: Marcadores de las 6 fases (uno por fase, tolera variantes de redacción).
PHASE_MARKERS = ("Load", "Research", "Design", "Spec", "TDD", "Docs")


def _skill_frontmatter() -> dict[str, object]:
    """Frontmatter YAML del SKILL.md del ciclo frontera."""
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---", 2)[1])


class TestFrontierSkill:
    """La skill es la fuente del procedimiento y debe pasar los gates de skill."""

    def test_skill_y_min_existen(self) -> None:
        """SKILL.md y SKILL.min.md existen y no están vacíos."""
        for name in ("SKILL.md", "SKILL.min.md"):
            path = SKILL_DIR / name
            assert path.is_file(), f"falta {path}"
            assert len(path.read_text(encoding="utf-8").strip()) > 200

    def test_frontmatter_obligatorio(self) -> None:
        """name/domain/version/project_agnostic/description cumplen la spec."""
        fm = _skill_frontmatter()
        assert fm["name"] == "frontier-engineering"
        assert fm["domain"] == "meta"
        assert fm["version"] == "1.0.0"
        assert fm["project_agnostic"] is True
        description = str(fm["description"])
        assert description.lower().startswith("usar cuando")
        assert len(description) <= 320, f"description {len(description)} > 320"

    def test_skill_cubre_las_seis_fases(self) -> None:
        """El cuerpo documenta las 6 fases y un ejemplo concreto."""
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        for marker in PHASE_MARKERS:
            assert marker in text, f"fase ausente en SKILL.md: {marker}"
        assert "## Ejemplo" in text

    def test_registry_declara_digest(self) -> None:
        """El registry registra la skill con sha256 (anti content-drift)."""
        registry = yaml.safe_load(
            (ROOT / ".opencode" / "skills" / "skills_registry.yaml").read_text(
                encoding="utf-8"
            )
        )
        entries = {
            item["name"]: item for item in registry.get("skills", []) if "name" in item
        }
        assert "frontier-engineering" in entries
        digest = str(entries["frontier-engineering"].get("sha256", ""))
        assert len(digest) == 64, "sha256 ausente o inválido en el registry"


class TestFrontierCommand:
    """El atajo `/frontera` debe ser autosuficiente (tarea + 6 fases + cierre)."""

    def test_comando_existe_y_recibe_argumentos(self) -> None:
        """El comando declara $ARGUMENTS y referencia la skill."""
        text = COMMAND.read_text(encoding="utf-8")
        assert "$ARGUMENTS" in text
        assert "frontier-engineering" in text

    def test_comando_enumera_fases_y_cierre(self) -> None:
        """Las 6 fases y el cierre (gates + docs + publish) están explícitos."""
        text = COMMAND.read_text(encoding="utf-8")
        for marker in PHASE_MARKERS:
            assert marker in text, f"fase ausente en el comando: {marker}"
        assert "publish.py" in text
        assert "docs/research/frontier-" in text


class TestAgentsHook:
    """`AGENTS.md` se inyecta en cada sesión: es la superficie de uso constante."""

    def test_seccion_ciclo_frontera_presente(self) -> None:
        """La sección existe y menciona el atajo y la skill canónica."""
        text = AGENTS_MD.read_text(encoding="utf-8")
        assert "## Ciclo Frontera (petición explícita)" in text
        assert "/frontera" in text
        assert "frontier-engineering" in text

    def test_seccion_conserva_fases_y_cierre(self) -> None:
        """La sección no pierde las fases ni el cierre con gates/publish."""
        section = AGENTS_MD.read_text(encoding="utf-8").split(
            "## Ciclo Frontera (petición explícita)", 1
        )[1].split("## Cómo trabajar aquí", 1)[0]
        for marker in PHASE_MARKERS:
            assert marker in section, f"fase ausente en AGENTS.md: {marker}"
        assert "publish.py" in section


class TestProjectConfigSync:
    """`project_config.yaml` debe reflejar el directorio real de skills."""

    def test_skill_total_incluye_frontier_engineering(self) -> None:
        """SKILLS.total == directorios reales y la lista contiene la skill."""
        config = yaml.safe_load(PROJECT_CONFIG.read_text(encoding="utf-8"))
        real = {
            path.name
            for path in (ROOT / ".opencode" / "skills").iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        }
        skills_cfg = config.get("SKILLS", {})
        assert skills_cfg.get("total") == len(real)
        assert "frontier-engineering" in set(skills_cfg.get("skill_list", []))
