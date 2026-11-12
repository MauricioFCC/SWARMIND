"""Contrato de la imagen del repositorio (README, hubs e índices de docs).

WHAT: README corto y veraz, hub de documentación Diátaxis, índices de
agentes/skills generados desde la SSOT y gate de enlaces internos.

WHY: la fachada del repo había derivado (42/25/7000 vs 49/26/7745); un
visitante recibía información falsa y el mantenedor pagaba deuda manual.

WHERE: harness/tests — lectura de docs + ejecución de scripts del repo.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(1, str(ROOT / "scripts"))

import check_docs_links as links
import gen_docs_index as index


class TestLinks:
    """El checker resuelve relativos y rutas mdbook, e ignora código."""

    def test_relativo_roto_y_valido(self, tmp_path: Path) -> None:
        """Detecta el roto y acepta el que existe."""
        (tmp_path / "ok.md").write_text("ok", encoding="utf-8")
        doc = tmp_path / "doc.md"
        doc.write_text("[ok](ok.md)\n[mal](missing.md)\n", encoding="utf-8")
        broken = links.check_files([doc])
        assert [item.target for item in broken] == ["missing.md"]

    def test_ruta_raiz_mdbook(self, tmp_path: Path) -> None:
        """`/assets/x` se resuelve contra docs/src/<lang>/."""
        base = tmp_path / "docs" / "src" / "es"
        (base / "assets").mkdir(parents=True)
        (base / "assets" / "logo.svg").write_text("<svg/>", encoding="utf-8")
        doc = base / "README.md"
        doc.write_text("[logo](/assets/logo.svg)\n", encoding="utf-8")
        assert links.check_files([doc]) == []

    def test_ignora_bloques_de_codigo(self, tmp_path: Path) -> None:
        """Un enlace dentro de un fence no es un enlace real."""
        doc = tmp_path / "doc.md"
        doc.write_text("```\n[no](missing.md)\n```\n", encoding="utf-8")
        assert links.check_files([doc]) == []

    def test_fachada_sin_rotos(self) -> None:
        """README, hubs y SUMMARY no tienen enlaces internos rotos."""
        assert links.check_files(links.default_paths()) == []


class TestIndexes:
    """Los catálogos se generan desde la SSOT y detectan drift."""

    def test_conteos_reales(self) -> None:
        """El índice declara los agentes y skills reales (26/49)."""
        agents = index._agents()
        skills = index._skills()
        assert len(agents) == 26
        assert len(skills) == 50
        assert "50 skills" in index.render_skills(skills)
        assert "26 agentes" in index.render_agents(agents)

    def test_archivos_al_dia(self) -> None:
        """`--check` no encuentra drift en los índices versionados."""
        assert index._sync(write=False) == 0


class TestReadme:
    """El README es la primera impresión: corto, veraz y navegable."""

    def test_longitud_y_secciones(self) -> None:
        """<= 260 líneas y secciones esenciales + diagrama Mermaid."""
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 260
        for section in ("## Quickstart", "## Architecture", "## Documentation",
                        "## Status and limitations"):
            assert section in text
        assert "```mermaid" in text

    def test_conteos_reales(self) -> None:
        """Declara 50 skills, 26 agentes y 7.7k tests; sin cifras viejas."""
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "50 skills" in text
        assert "26 agents" in text
        assert "7.7k" in text
        for stale in ("42 skills", "25 agents", "7000+", "0 files over 500"):
            assert stale not in text


class TestDocsHub:
    """`docs/README.md` es el mapa Diátaxis y SUMMARY apunta a los índices."""

    def test_hub_diataxis(self) -> None:
        """Existen las cuatro categorías y enlaces a ES/EN y roadmap."""
        text = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        for term in ("Tutorial", "How-to", "Reference", "Explanation"):
            assert term in text
        assert "docs/src/es/README.md" in text
        assert "docs/src/es/roadmap/estado.md" in text

    def test_summary_sin_catalogos_manuales(self) -> None:
        """SUMMARY no enumera 20 agentes/34 skills: usa los índices."""
        text = (ROOT / "docs" / "src" / "es" / "SUMMARY.md").read_text(encoding="utf-8")
        assert "(20)" not in text and "(34)" not in text
        assert "agents/INDEX.md" in text
        assert "skills/INDEX.md" in text
        assert "roadmap/estado.md" in text
