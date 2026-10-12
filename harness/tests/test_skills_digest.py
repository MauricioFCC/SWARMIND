"""Tests TDD para digests sha256 de skills (FR-D1, ADR-0103).

Cubre:
  (a) ``hash_skills_registry.compute_skill_digest``: estable, incluye scripts/
      en orden canonico y detecta mutacion de cualquier archivo cubierto.
  (b) ``validate_skills._validate_skill``: digest correcto -> sin error;
      digest incorrecto -> error de content drift; sin digest -> warning.
  (c) CLI ``hash_skills_registry --dry-run`` no escribe; ``--write`` si.
  (d) Mutation-style: la verificacion de digest discrimina (si se elimina la
      comparacion, el caso "incorrecto" deja de detectarse).

Todo aislado en ``tmp_path`` con monkeypatch de ``_SKILLS_DIR``/``_REGISTRY``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ esta fuera de harness/ -> lo agregamos al path de import.
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(1, str(_SCRIPTS))

import hash_skills_registry as hsr
import validate_skills as vs

# ===========================================================================
# Helpers
# ===========================================================================


def _frontmatter(name: str) -> str:
    """Frontmatter valido para el validador de skills (SDO + convenciones)."""
    return (
        f"name: {name}\n"
        "description: Usar cuando el usuario pruebe el digest del test.\n"
        "version: 1.0.0\n"
        "project_agnostic: true\n"
    )


def _make_skill(root: Path, name: str, *, with_scripts: bool = True) -> Path:
    """Crea una skill de prueba (SKILL.md + SKILL.min.md + scripts/) en disco.

    Args:
        root: Directorio raiz que actua como ``.opencode/skills``.
        name: Nombre de la skill.
        with_scripts: Si True, agrega scripts/x.py.

    Returns:
        Ruta al directorio de la skill.
    """
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\n{_frontmatter(name)}---\n# {name}\n", encoding="utf-8"
    )
    (skill_dir / "SKILL.min.md").write_text(
        f"---\nname: {name}\ndescription: Usar cuando se pruebe el test.\n---\n",
        encoding="utf-8",
    )
    if with_scripts:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        (scripts_dir / "x.py").write_text("# script x\n", encoding="utf-8")
    return skill_dir


def _registry_text(name: str, sha256: str | None = None) -> str:
    """Construye el texto de un registry minimo con una skill."""
    lines = [
        "skills:",
        f"  - name: {name}",
        "    domain: test",
        "    description: Usar cuando el usuario pruebe el digest del test.",
        "    version: 1.0.0",
        "    project_agnostic: true",
    ]
    if sha256 is not None:
        lines.append(f"    sha256: {sha256}")
    return "\n".join(lines) + "\n"


# ===========================================================================
# (a) compute_skill_digest
# ===========================================================================


def test_digest_estable_entre_corridas(tmp_path: Path) -> None:
    """(a) Dos corridas sobre el mismo estado -> mismo digest hex de 64 chars."""
    skill_dir = _make_skill(tmp_path, "skill-a")

    first = hsr.compute_skill_digest(skill_dir)
    second = hsr.compute_skill_digest(skill_dir)

    assert first == second
    assert len(first) == 64
    assert all(c in "0123456789abcdef" for c in first)


def test_digest_cambia_al_mutar_skill_md(tmp_path: Path) -> None:
    """(a) Mutar SKILL.md cambia el digest (detecta drift del cuerpo)."""
    skill_dir = _make_skill(tmp_path, "skill-b")
    before = hsr.compute_skill_digest(skill_dir)

    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(skill_md.read_text(encoding="utf-8") + "\nlinea nueva\n", encoding="utf-8")

    assert hsr.compute_skill_digest(skill_dir) != before


def test_digest_cambia_al_mutar_min_md(tmp_path: Path) -> None:
    """(a) Mutar SKILL.min.md cambia el digest (progressive disclosure cubierta)."""
    skill_dir = _make_skill(tmp_path, "skill-min")
    before = hsr.compute_skill_digest(skill_dir)

    (skill_dir / "SKILL.min.md").write_text("---\nname: skill-min\n---\ncambio\n", encoding="utf-8")

    assert hsr.compute_skill_digest(skill_dir) != before


def test_digest_incluye_scripts(tmp_path: Path) -> None:
    """(a) scripts/ forma parte del digest (supply-chain de skills)."""
    skill_dir = _make_skill(tmp_path, "skill-c")
    before = hsr.compute_skill_digest(skill_dir)

    (skill_dir / "scripts" / "x.py").write_text("# script x modificado\n", encoding="utf-8")

    assert hsr.compute_skill_digest(skill_dir) != before


def test_digest_orden_canonico_scripts(tmp_path: Path) -> None:
    """(a) Con varios scripts, el digest es estable (orden canonico determinista)."""
    skill_dir = _make_skill(tmp_path, "skill-d")
    scripts_dir = skill_dir / "scripts"
    (scripts_dir / "a.py").write_text("A\n", encoding="utf-8")
    (scripts_dir / "b.py").write_text("B\n", encoding="utf-8")

    assert hsr.compute_skill_digest(skill_dir) == hsr.compute_skill_digest(skill_dir)


# ===========================================================================
# (b) validate_skills: verificacion del digest
# ===========================================================================


def test_validator_digest_correcto_sin_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(b) Registry con sha256 correcto -> sin error de drift."""
    skill_dir = _make_skill(tmp_path, "skill-ok")
    digest = hsr.compute_skill_digest(skill_dir)
    registry = tmp_path / "skills_registry.yaml"
    registry.write_text(_registry_text("skill-ok", digest), encoding="utf-8")

    monkeypatch.setattr(vs, "_SKILLS_DIR", tmp_path)
    monkeypatch.setattr(vs, "_REGISTRY", registry)

    errors = vs._validate_skill(skill_dir, quiet=True)

    assert not any("sha256" in e for e in errors)
    assert errors == []


def test_validator_digest_incorrecto_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(b) Digest obsoleto tras modificar el skill -> error de content drift."""
    skill_dir = _make_skill(tmp_path, "skill-drift")
    digest = hsr.compute_skill_digest(skill_dir)
    registry = tmp_path / "skills_registry.yaml"
    registry.write_text(_registry_text("skill-drift", digest), encoding="utf-8")

    # El skill cambia DESPUES de hashear -> el registry queda obsoleto.
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(skill_md.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")

    monkeypatch.setattr(vs, "_SKILLS_DIR", tmp_path)
    monkeypatch.setattr(vs, "_REGISTRY", registry)

    errors = vs._validate_skill(skill_dir, quiet=True)

    assert any("no coincide" in e and "drift" in e for e in errors)


def test_validator_sin_digest_warning_no_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """(b) Registry sin sha256 -> warning informativo, NO error (migracion)."""
    skill_dir = _make_skill(tmp_path, "skill-nod")
    registry = tmp_path / "skills_registry.yaml"
    registry.write_text(_registry_text("skill-nod"), encoding="utf-8")

    monkeypatch.setattr(vs, "_SKILLS_DIR", tmp_path)
    monkeypatch.setattr(vs, "_REGISTRY", registry)

    errors = vs._validate_skill(skill_dir, quiet=False)
    out = capsys.readouterr().out

    assert errors == []
    assert "sha256" in out


# ===========================================================================
# (c) CLI: --dry-run no escribe, --write escribe
# ===========================================================================


def test_cli_dry_run_no_escribe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(c) --dry-run no modifica el archivo del registry."""
    _make_skill(tmp_path, "skill-run")
    registry = tmp_path / "skills_registry.yaml"
    registry.write_text(_registry_text("skill-run"), encoding="utf-8")
    before = registry.read_text(encoding="utf-8")

    monkeypatch.setattr(hsr, "_SKILLS_DIR", tmp_path)
    monkeypatch.setattr(hsr, "_REGISTRY", registry)
    monkeypatch.setattr(sys, "argv", ["hash_skills_registry.py", "--dry-run"])

    hsr.main()

    assert registry.read_text(encoding="utf-8") == before


def test_cli_write_escribe_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(c) --write persiste el digest y es idempotente."""
    skill_dir = _make_skill(tmp_path, "skill-w")
    expected = hsr.compute_skill_digest(skill_dir)
    registry = tmp_path / "skills_registry.yaml"
    registry.write_text(_registry_text("skill-w"), encoding="utf-8")

    monkeypatch.setattr(hsr, "_SKILLS_DIR", tmp_path)
    monkeypatch.setattr(hsr, "_REGISTRY", registry)
    monkeypatch.setattr(sys, "argv", ["hash_skills_registry.py", "--write"])

    hsr.main()

    written = registry.read_text(encoding="utf-8")
    assert f"sha256: {expected}" in written

    # Idempotencia: una segunda corrida no reescribe (mismo contenido).
    hsr.main()
    assert registry.read_text(encoding="utf-8") == written


# ===========================================================================
# (d) Mutation-style: el oraculo discrimina
# ===========================================================================


def test_mutation_verificacion_digest_discrimina(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(d) Mutation-style: correcto->0 errores, incorrecto->error.

    Si se elimina la linea de comparacion del validador, el caso incorrecto
    dejaria de producir error y este test fallaria.
    """
    skill_dir = _make_skill(tmp_path, "skill-mut")
    good = hsr.compute_skill_digest(skill_dir)
    registry = tmp_path / "skills_registry.yaml"
    monkeypatch.setattr(vs, "_SKILLS_DIR", tmp_path)
    monkeypatch.setattr(vs, "_REGISTRY", registry)

    # Digest correcto -> sin error.
    registry.write_text(_registry_text("skill-mut", good), encoding="utf-8")
    assert vs._validate_skill(skill_dir, quiet=True) == []

    # Digest incorrecto -> error de drift.
    registry.write_text(_registry_text("skill-mut", "0" * 64), encoding="utf-8")
    errors = vs._validate_skill(skill_dir, quiet=True)
    assert any("drift" in e for e in errors)
