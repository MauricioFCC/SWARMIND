"""Contrato de las skills jurídicas/forenses (propuesta 2026-11-06).

WHAT: las 5 skills core deben cumplir el contrato Agent Skills + PEC, estar
registradas y enrutar sin ambigüedad a un agente real. Se exige el aviso de
revisión humana y la política de citas verificadas.

WHY: en dominio jurídico una omisión o una cita inventada invalida una
actuación; el contrato convierte esa exigencia en un gate ejecutable.

WHERE: harness/tests — solo lectura sobre ``.opencode``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / ".opencode" / "skills"
AGENTS = ROOT / ".opencode" / "agents"
CONFIG = ROOT / ".opencode" / "config" / "project_config.yaml"
REGISTRY = SKILLS / "skills_registry.yaml"

LEGAL = {
    "legal-forensics": "cadena de custodia",
    "legal-evidence-audit": "material probatorio",
    "legal-procedure-co": "debido proceso",
    "legal-drafting-co": "demanda",
    "legal-jurisprudence-co": "jurisprudencia",
}
MAX_DESCRIPTION = 320


def _frontmatter(name: str) -> dict[str, object]:
    """Frontmatter YAML del SKILL.md."""
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---", 2)[1])


class TestContract:
    """Estructura y frontmatter de las 5 skills."""

    def test_archivos_existen(self) -> None:
        """Cada skill tiene SKILL.md, SKILL.min.md y spec generado."""
        for name in LEGAL:
            assert (SKILLS / name / "SKILL.md").is_file(), name
            assert (SKILLS / name / "SKILL.min.md").is_file(), name
            assert (SKILLS / name / "SKILL.spec.json").is_file(), name

    def test_frontmatter_legal(self) -> None:
        """name/domain/version/license/project_agnostic son correctos."""
        for name in LEGAL:
            fm = _frontmatter(name)
            meta = fm["metadata"]
            assert isinstance(meta, dict)
            assert fm["name"] == name
            assert meta["domain"] == "legal"
            assert meta["version"] == "1.0.0"
            assert fm["license"] == "MIT"
            assert meta["project_agnostic"] == "true"

    def test_description_pushy_y_acotada(self) -> None:
        """Empieza por 'Usar cuando', cabe en 320 y declara alcance."""
        for name in LEGAL:
            description = str(_frontmatter(name)["description"])
            assert description.lower().startswith("usar cuando")
            assert len(description) <= MAX_DESCRIPTION
            assert "Alcance:" in description
            assert "ver legal-" in description


class TestContent:
    """PEC, ejemplo y límites de seguridad jurídica."""

    def test_pec_y_canon(self) -> None:
        """Cada skill declara persona senior y >=2 fuentes https."""
        for name in LEGAL:
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            assert "PERSONA & CANON" in text
            body = text.split("PERSONA & CANON", 1)[1]
            assert "senior" in body.lower() or "12+" in body
            assert body.count("https://") >= 2

    def test_ejemplo_y_checklist(self) -> None:
        """Toda skill demuestra el patrón con ejemplo y checklist."""
        for name in LEGAL:
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            assert "## Ejemplo" in text
            assert "- [ ]" in text

    def test_revision_humana_obligatoria(self) -> None:
        """Ninguna conclusión jurídica se presenta sin revisión humana."""
        for name in LEGAL:
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8").lower()
            assert "revisión humana" in text or "revision humana" in text

    def test_min_es_menor(self) -> None:
        """SKILL.min.md es una versión N1 más corta que el SKILL.md."""
        for name in LEGAL:
            full = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            mini = (SKILLS / name / "SKILL.min.md").read_text(encoding="utf-8")
            assert len(mini.splitlines()) < len(full.splitlines())


class TestRegistryAndRouting:
    """Registro, conteos y enrutado a agentes reales."""

    def test_registry_con_digest(self) -> None:
        """Las 5 skills están en el registry con sha256."""
        data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
        entries = {item["name"]: item for item in data["skills"]}
        for name in LEGAL:
            assert name in entries
            assert len(str(entries[name].get("sha256", ""))) == 64

    def test_config_cuenta_50(self) -> None:
        """project_config declara 50 skills e incluye las nuevas."""
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        assert config["SKILLS"]["total"] == 50
        listed = set(config["SKILLS"]["skill_list"])
        assert set(LEGAL) <= listed

    def test_routing_a_agentes_reales(self) -> None:
        """SKILL_TO_AGENT y DOMAIN_SKILLS cubren las 5 con agentes reales."""
        from harness.orchestrator.skill_bundler import DOMAIN_SKILLS, SKILL_TO_AGENT

        real = {
            path.stem for path in AGENTS.glob("*.md") if not path.name.endswith(".min.md")
        }
        for name in LEGAL:
            assert SKILL_TO_AGENT[name] in real
            assert name in DOMAIN_SKILLS["legal"]

    def test_keywords_de_disparo(self) -> None:
        """Cada skill contiene su keyword de routing en la description."""
        for name, keyword in LEGAL.items():
            description = str(_frontmatter(name)["description"]).lower()
            assert keyword in description, (name, keyword)
