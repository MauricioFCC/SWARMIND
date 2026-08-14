"""
Tests TDD para scripts/deploy_all.py — deploy & sync (Opción A SSOT global).

Cubre el deploy dinámico de skills/agentes a proyectos de DEV-SPACE:
  - _discover_skills: descubre desde .opencode/skills/ (SSOT, sin hardcode)
  - _discover_agents: descubre desde .opencode/agents/ (excluye .min.md)
  - deploy_skills: copia TODAS las skills + registry, limpia obsoletas
    (fix: diagram-design/swarm-release-ops ya no se borran del mirror)
  - generate_readme: usa conteos dinámicos (22 agentes, N skills)
  - _detect_type / resolve_project / discover_projects
  - _sync_tree: sync preservador sin borrar config propia
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(1, str(_SCRIPTS))

import deploy_all as da

# ===========================================================================
# Fixtures — árboles aislados (no tocan DEV-SPACE real)
# ===========================================================================


@pytest.fixture
def fake_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Crea un SWARMIND falso con .opencode/skills + agents y redirige _ROOT."""
    root = tmp_path / "swarmind"
    # Skills de la fuente (3 + auto)
    for skill in ("alpha-research", "diagram-design", "swarm-release-ops"):
        (root / ".opencode" / "skills" / skill).mkdir(parents=True)
        (root / ".opencode" / "skills" / skill / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: Usar cuando se pruebe el deploy.\n---\n",
            encoding="utf-8",
        )
    (root / ".opencode" / "skills" / "auto").mkdir(parents=True)
    (root / ".opencode" / "skills" / "auto" / "gen.md").write_text("# auto\n", encoding="utf-8")
    (root / ".opencode" / "skills" / "skills_registry.yaml").write_text(
        "skills:\n  - name: alpha-research\n  - name: diagram-design\n  - name: swarm-release-ops\n",
        encoding="utf-8",
    )
    # Agentes de la fuente (2 + 1 .min)
    (root / ".opencode" / "agents").mkdir(parents=True)
    (root / ".opencode" / "agents" / "builder.md").write_text("# builder\n", encoding="utf-8")
    (root / ".opencode" / "agents" / "coordinator.md").write_text("# coordinator\n", encoding="utf-8")
    (root / ".opencode" / "agents" / "builder.min.md").write_text("# min\n", encoding="utf-8")

    monkeypatch.setattr(da, "_ROOT", root)
    return root


@pytest.fixture
def fake_project(tmp_path: Path) -> da.Project:
    """Proyecto destino aislado."""
    proj = tmp_path / "proj-test"
    (proj / ".opencode" / "skills").mkdir(parents=True)
    return da.Project(name="proj-test", path=proj, ptype="general", description="test")


# ===========================================================================
# _discover_skills / _discover_agents (dinámicos, sin hardcode)
# ===========================================================================


def test_discover_skills_dinamico(fake_root: Path) -> None:
    """Descubre las skills del disco (excluye auto/)."""
    skills = da._discover_skills()

    assert skills == ["alpha-research", "diagram-design", "swarm-release-ops"]
    assert "auto" not in skills


def test_discover_skills_incluye_nuevas(fake_root: Path) -> None:
    """Una skill nueva en disco se descubre automáticamente (fix del bug 31→33)."""
    (fake_root / ".opencode" / "skills" / "nueva-skill").mkdir()
    (fake_root / ".opencode" / "skills" / "nueva-skill" / "SKILL.md").write_text(
        "---\nname: nueva-skill\ndescription: Usar cuando se pruebe.\n---\n", encoding="utf-8"
    )

    skills = da._discover_skills()

    assert "nueva-skill" in skills
    assert len(skills) == 4


def test_discover_agents_dinamico(fake_root: Path) -> None:
    """Descubre agentes excluyendo los .min.md."""
    agents = da._discover_agents()

    assert agents == ["builder", "coordinator"]
    assert "builder.min" not in agents


def test_discover_agents_sin_min(fake_root: Path) -> None:
    """Ningun agente descubierto termina en .min (no duplicar)."""
    agents = da._discover_agents()

    assert all(not a.endswith(".min") for a in agents)


def test_discover_sin_directorio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Si .opencode/skills no existe -> lista vacia (no crashea)."""
    monkeypatch.setattr(da, "_ROOT", tmp_path / "nada")

    assert da._discover_skills() == []
    assert da._discover_agents() == []


# ===========================================================================
# deploy_skills — copia todas + limpia obsoletas (sin borrar las nuevas)
# ===========================================================================


def test_deploy_skills_copia_todas(fake_root: Path, fake_project: da.Project) -> None:
    """Despliega TODAS las skills de la fuente al proyecto."""
    copied = da.deploy_skills(fake_project, dry_run=False)

    assert copied == 3
    for skill in ("alpha-research", "diagram-design", "swarm-release-ops"):
        assert (fake_project.path / ".opencode" / "skills" / skill / "SKILL.md").is_file()
    # registry copiado
    assert (fake_project.path / ".opencode" / "skills" / "skills_registry.yaml").is_file()


def test_deploy_skills_no_borra_nuevas(fake_root: Path, fake_project: da.Project) -> None:
    """Fix del bug: skills nuevas (diagram-design) NO se borran como obsoletas.

    Precondición: el proyecto ya tiene las skills viejas + las nuevas del
    deploy anterior. deploy_skills no debe borrar las que están en la fuente.
    """
    da.deploy_skills(fake_project, dry_run=False)
    # simular un segundo deploy
    copied2 = da.deploy_skills(fake_project, dry_run=False)

    assert copied2 == 3
    assert (fake_project.path / ".opencode" / "skills" / "diagram-design" / "SKILL.md").is_file()


def test_deploy_skills_limpia_obsoletas(fake_root: Path, fake_project: da.Project) -> None:
    """Una skill en el proyecto que ya no esta en la fuente -> se limpia."""
    # skill obsoleta en el proyecto (no existe en la fuente)
    obsolete = fake_project.path / ".opencode" / "skills" / "skill-vieja"
    obsolete.mkdir()
    (obsolete / "SKILL.md").write_text("---\nname: skill-vieja\n---\n", encoding="utf-8")

    da.deploy_skills(fake_project, dry_run=False)

    assert not obsolete.exists()
    assert (fake_project.path / ".opencode" / "skills" / "alpha-research" / "SKILL.md").is_file()


def test_deploy_skills_preserva_auto(fake_root: Path, fake_project: da.Project) -> None:
    """El directorio auto/ (skills auto-generadas) se preserva."""
    auto = fake_project.path / ".opencode" / "skills" / "auto"
    auto.mkdir(parents=True)
    (auto / "gen.md").write_text("# auto\n", encoding="utf-8")

    da.deploy_skills(fake_project, dry_run=False)

    assert auto.is_dir()
    assert (auto / "gen.md").is_file()


def test_deploy_skills_dry_run(fake_root: Path, fake_project: da.Project) -> None:
    """dry_run devuelve el conteo pero no escribe nada."""
    copied = da.deploy_skills(fake_project, dry_run=True)

    assert copied == 3
    assert not (fake_project.path / ".opencode" / "skills" / "alpha-research").exists()


# ===========================================================================
# generate_readme — conteos dinámicos
# ===========================================================================


def test_generate_readme_conteos_dinamicos(fake_root: Path, fake_project: da.Project) -> None:
    """README usa conteos reales (22 agentes / N skills), no hardcode."""
    da.generate_readme(fake_project, dry_run=False)
    content = (fake_project.path / "README.md").read_text(encoding="utf-8")

    assert "Agentes (2)" in content
    assert "Skills (3" in content
    assert "alpha-research" in content
    assert "diagram-design" in content
    assert "builder" in content
    assert "coordinator" in content
    assert "Agentes (20)" not in content  # hardcode viejo


def test_generate_readme_dry_run_no_escribe(fake_root: Path, fake_project: da.Project) -> None:
    """dry_run no escribe README."""
    da.generate_readme(fake_project, dry_run=True)

    assert not (fake_project.path / "README.md").exists()


# ===========================================================================
# _detect_type / resolve_project / discover_projects
# ===========================================================================


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("core-quant-engine", "trading"),
        ("Onyx-Quan-AIBot", "trading"),
        ("Historia Clinica", "healthtech"),
        ("PDV Basic", "retail"),
        ("sugurityOs", "security"),
        ("proyecto-aleatorio", "general"),
    ],
)
def test_detect_type(name: str, expected: str) -> None:
    """Infere el tipo de proyecto desde el nombre."""
    assert da._detect_type(name) == expected


def test_resolve_project_por_alias() -> None:
    """Alias CLI (CQE, PDV...) resuelve al proyecto real."""
    projects = [
        da.Project(name="core-quant-engine", path=Path("x"), ptype="trading", description=""),
        da.Project(name="PDV Basic", path=Path("y"), ptype="retail", description=""),
    ]

    assert da.resolve_project("CQE", projects).name == "core-quant-engine"  # type: ignore[union-attr]
    assert da.resolve_project("PDV", projects).name == "PDV Basic"  # type: ignore[union-attr]
    assert da.resolve_project("core-quant-engine", projects).name == "core-quant-engine"  # type: ignore[union-attr]


def test_resolve_project_no_encontrado() -> None:
    """Selector invalido -> None (sin crash)."""
    projects = [da.Project(name="core-quant-engine", path=Path("x"), ptype="trading", description="")]

    assert da.resolve_project("NO-EXISTE", projects) is None
    assert da.resolve_project("", projects) is None


def test_discover_projects_solo_con_opencode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Solo proyectos con .opencode/ se descubren (estándar v2.5)."""
    dev = tmp_path / "DEV-SPACE"
    (dev / "proj-a" / ".opencode").mkdir(parents=True)
    (dev / "proj-b").mkdir()  # sin .opencode -> ignorado
    (dev / "SWARMIND").mkdir()  # skip dir -> ignorado
    monkeypatch.setattr(da, "_DEV_SPACE", dev)

    projects = da.discover_projects()

    assert [p.name for p in projects] == ["proj-a"]


# ===========================================================================
# _sync_tree — sync preservador
# ===========================================================================


def test_sync_tree_copia_y_preserva(tmp_path: Path) -> None:
    """Copia src→dst y NO borra archivos propios del destino."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "a").mkdir(parents=True)
    (src / "a" / "file1.md").write_text("1", encoding="utf-8")
    (src / "b").mkdir()
    (src / "b" / "file2.md").write_text("2", encoding="utf-8")
    # archivo propio del proyecto (no en src) -> debe preservarse
    dst.mkdir()
    (dst / "propio.yaml").write_text("x", encoding="utf-8")

    count = da._sync_tree(src, dst)

    assert (dst / "a" / "file1.md").is_file()
    assert (dst / "b" / "file2.md").is_file()
    assert (dst / "propio.yaml").is_file()  # preservado
    assert count == 2


def test_sync_tree_dry_run_no_escribe(tmp_path: Path) -> None:
    """dry_run cuenta pero no escribe."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "a").mkdir(parents=True)
    (src / "a" / "file1.md").write_text("1", encoding="utf-8")

    count = da._sync_tree(src, dst, dry_run=True)

    assert count == 1
    assert not (dst / "a" / "file1.md").exists()
