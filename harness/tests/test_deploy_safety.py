"""Tests del deploy NO DESTRUCTIVO por proyecto (politica + guard anti-TDR).

WHAT: valida que ``scripts/deploy_all.py`` respeta la curacion de los
proyectos hermanos (modos mirror/add-only/skip, exclude) y que el guard
anti-TDR aborta re-propagar ``num_ctx=16384`` (causa del BSOD 0x116).
WHY: el bug reproducido forzaba a Onyx de 17 -> 35 skills y el sync global
podia sobreescribir curacion sin aviso.
WHERE: ``harness/tests/test_deploy_safety.py`` (hermetico, tmp_path).

Cada test puede FALLAR si se elimina la politica o el guard (no decorativos).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(1, str(_SCRIPTS))

import deploy_all as da

_SKILL_MD = "---\nname: {name}\nversion: {version}\n---\n"


def _write_skill(base: Path, name: str, version: str = "fuente") -> None:
    """Crea una skill minima con SKILL.md en ``base/skills/<name>``.

    Args:
        base: Raiz que contiene ``.opencode/skills``.
        name: Nombre de la skill.
        version: Version marcadora para detectar sobrescritura.
    """
    skill = base / ".opencode" / "skills" / name
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(_SKILL_MD.format(name=name, version=version), encoding="utf-8")


def _write_policy(project: da.Project, body: str) -> None:
    """Escribe ``<proyecto>/.opencode/deploy.yaml`` con el cuerpo dado.

    Args:
        project: Proyecto destino.
        body: Contenido YAML de la politica.
    """
    policy = project.path / ".opencode" / "deploy.yaml"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(body, encoding="utf-8")


@pytest.fixture
def fake_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fuente Swarmind falsa con skills ``keep`` y ``skipme``.

    Args:
        tmp_path: Directorio temporal de pytest.
        monkeypatch: Patch de ``_ROOT`` y del set de avisos.

    Returns:
        Raiz de la fuente falsa.
    """
    root = tmp_path / "swarmind"
    _write_skill(root, "keep")
    _write_skill(root, "skipme")
    (root / ".opencode" / "skills" / "auto").mkdir(parents=True)
    monkeypatch.setattr(da, "_ROOT", root)
    monkeypatch.setattr(da, "_POLICY_WARNED", set())
    return root


@pytest.fixture
def project(tmp_path: Path) -> da.Project:
    """Proyecto destino aislado con ``.opencode/skills``.

    Args:
        tmp_path: Directorio temporal de pytest.

    Returns:
        Project apuntando al directorio temporal.
    """
    path = tmp_path / "proyecto-cur"
    (path / ".opencode" / "skills").mkdir(parents=True)
    return da.Project(name="proyecto-cur", path=path, ptype="general", description="test")


def _skill_file(project: da.Project, name: str) -> Path:
    """Ruta al SKILL.md de una skill del proyecto.

    Args:
        project: Proyecto destino.
        name: Nombre de la skill.

    Returns:
        Path del SKILL.md (puede no existir).
    """
    return project.path / ".opencode" / "skills" / name / "SKILL.md"


# ===========================================================================
# (a) mode: skip -> no toca skills
# ===========================================================================


def test_mode_skip_no_toca_skills(fake_root: Path, project: da.Project) -> None:
    """mode=skip deja skills/ intacto y no anade las de la fuente."""
    _write_skill(project.path, "keep", version="curado")
    _write_skill(project.path, "solo-mio", version="curado")
    _write_policy(project, "skills:\n  mode: skip\n")

    stats = da.deploy_project(project, dry_run=False, sync_only=True)

    assert stats["skills_deployed"] == 0
    assert "curado" in _skill_file(project, "keep").read_text(encoding="utf-8")
    assert _skill_file(project, "solo-mio").is_file()
    assert not _skill_file(project, "skipme").exists()


# ===========================================================================
# (b) add-only -> no borra ni sobrescribe, pero anade
# ===========================================================================


def test_add_only_no_borra_no_sobrescribe_pero_anade(
    fake_root: Path, project: da.Project
) -> None:
    """add-only conserva curadas, sobrescribe nada y anade la faltante."""
    _write_skill(project.path, "keep", version="curado")
    _write_skill(project.path, "solo-mio", version="curado")
    _write_policy(project, "skills:\n  mode: add-only\n")

    stats = da.deploy_project(project, dry_run=False, sync_only=True)

    assert stats["skills_deployed"] == 1  # solo skipme faltaba
    assert "curado" in _skill_file(project, "keep").read_text(encoding="utf-8")
    assert _skill_file(project, "solo-mio").is_file()
    assert _skill_file(project, "skipme").is_file()


# ===========================================================================
# (c) exclude respetado en copia y limpieza
# ===========================================================================


def test_exclude_respetado_en_copia_y_limpieza(
    fake_root: Path, project: da.Project
) -> None:
    """skills.exclude no se copia/sobrescribe y evita la limpieza."""
    _write_skill(project.path, "skipme", version="curado")
    _write_skill(project.path, "obsoleta", version="viejo")
    _write_policy(project, "skills:\n  mode: mirror\n  exclude: [skipme]\n")

    da.deploy_project(project, dry_run=False, sync_only=True)

    assert "curado" in _skill_file(project, "skipme").read_text(encoding="utf-8")
    assert not _skill_file(project, "obsoleta").exists()
    assert _skill_file(project, "keep").is_file()


def test_opencode_exclude_no_copia_ni_borra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """opencode.exclude no copia la ruta y preserva la existente en destino."""
    root = tmp_path / "swarmind"
    (root / ".opencode" / "config").mkdir(parents=True)
    (root / ".opencode" / "config" / "mi-config.yaml").write_text("src", encoding="utf-8")
    (root / ".opencode" / "config" / "otro.yaml").write_text("src", encoding="utf-8")
    monkeypatch.setattr(da, "_ROOT", root)
    monkeypatch.setattr(da, "_POLICY_WARNED", set())

    path = tmp_path / "proj"
    (path / ".opencode" / "config").mkdir(parents=True)
    (path / ".opencode" / "config" / "mi-config.yaml").write_text("curado", encoding="utf-8")
    (path / ".opencode" / "deploy.yaml").write_text(
        "opencode:\n  exclude: [config/mi-config.yaml]\n", encoding="utf-8"
    )
    project = da.Project(name="proj", path=path, ptype="general", description="")

    da.deploy_project(project, dry_run=False, sync_only=True)

    assert (path / ".opencode" / "config" / "mi-config.yaml").read_text(
        encoding="utf-8"
    ) == "curado"
    assert (path / ".opencode" / "config" / "otro.yaml").read_text(encoding="utf-8") == "src"


# ===========================================================================
# (d) default sin archivo = mirror + warning una sola vez
# ===========================================================================


def test_default_sin_archivo_es_mirror(
    fake_root: Path, project: da.Project, caplog: pytest.LogCaptureFixture
) -> None:
    """Sin deploy.yaml aplica mirror (compat) y avisa una sola vez."""
    _write_skill(project.path, "obsoleta", version="viejo")
    caplog.set_level(logging.WARNING, logger="deploy_all")

    da.deploy_project(project, dry_run=False, sync_only=True)
    da.deploy_project(project, dry_run=False, sync_only=True)

    assert not _skill_file(project, "obsoleta").exists()
    assert _skill_file(project, "keep").is_file()
    assert sum("sin .opencode/deploy.yaml" in r.message for r in caplog.records) == 1


# ===========================================================================
# (e) --force-mirror ignora politica
# ===========================================================================


def test_force_mirror_ignora_politica(fake_root: Path, project: da.Project) -> None:
    """force_mirror=True aplica mirror aunque la politica diga skip."""
    _write_skill(project.path, "obsoleta", version="viejo")
    _write_policy(project, "skills:\n  mode: skip\n")

    da.deploy_project(project, dry_run=False, sync_only=True, force_mirror=True)

    assert not _skill_file(project, "obsoleta").exists()
    assert _skill_file(project, "keep").is_file()
    assert _skill_file(project, "skipme").is_file()


def test_deploy_skills_force_mirror_ignora_policy_obj(fake_root: Path, project: da.Project) -> None:
    """deploy_skills con force_mirror ignora la politica declarada (skip)."""
    _write_policy(project, "skills:\n  mode: skip\n")
    copied = da.deploy_skills(project, dry_run=False, force_mirror=True)

    assert copied == 2
    assert _skill_file(project, "keep").is_file()


# ===========================================================================
# (f) guard anti-TDR aborta num_ctx 16384
# ===========================================================================


def test_guard_aborta_opencode_json_con_num_ctx_16384(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """El guard bloquea escribir opencode.json con num_ctx=16384 y marca blocked."""
    root = tmp_path / "swarmind"
    (root / ".opencode").mkdir(parents=True)
    (root / ".opencode" / "opencode.json").write_text(
        '{"options": {"num_ctx": 16384}}\n', encoding="utf-8"
    )
    monkeypatch.setattr(da, "_ROOT", root)
    monkeypatch.setattr(da, "_POLICY_WARNED", set())

    path = tmp_path / "proj"
    (path / ".opencode").mkdir(parents=True)
    (path / ".opencode" / "opencode.json").write_text(
        '{"options": {"num_ctx": 8192}}\n', encoding="utf-8"
    )
    project = da.Project(name="proj", path=path, ptype="general", description="")

    stats = da.deploy_project(project, dry_run=False, sync_only=True)

    assert stats["status"] == "blocked"
    assert "8192" in (path / ".opencode" / "opencode.json").read_text(encoding="utf-8")


def test_guard_permite_num_ctx_seguro(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un opencode.json con num_ctx=8192 se copia sin bloqueo."""
    root = tmp_path / "swarmind"
    (root / ".opencode").mkdir(parents=True)
    (root / ".opencode" / "opencode.json").write_text(
        '{"options": {"num_ctx": 8192}}\n', encoding="utf-8"
    )
    monkeypatch.setattr(da, "_ROOT", root)
    monkeypatch.setattr(da, "_POLICY_WARNED", set())

    path = tmp_path / "proj"
    (path / ".opencode").mkdir(parents=True)
    project = da.Project(name="proj", path=path, ptype="general", description="")

    stats = da.deploy_project(project, dry_run=False, sync_only=True)

    assert stats["status"] == "ok"
    assert (path / ".opencode" / "opencode.json").is_file()
