"""
Tests TDD para scripts/validate_skills.py — validador CLI de skills (ADR-0046/0047).

Cubre el validador de skills de SWARMIND que implementa:
  - spec Agent Skills Linux Foundation (frontmatter obligatorio name+description)
  - convencion SWARMIND (version, project_agnostic, SKILL.min.md, registry)
  - SDO (Skill Discovery Optimization, ADR-0047): description debe empezar
    con "Usar cuando" (condicion de disparo, no resumen de workflow)
  - referencias no rotas, registry sincronizado, tamano <500 lineas
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ esta fuera de harness/ -> lo agregamos al path de import
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(1, str(_SCRIPTS))

import validate_skills as vs

# ===========================================================================
# Helpers
# ===========================================================================


def _write_skill(root: Path, dirname: str, frontmatter: str, body: str = "# Skill\n") -> Path:
    """Escribe un skill de prueba y retorna la ruta a su SKILL.md."""
    skill_dir = root / dirname
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")
    (skill_dir / "SKILL.min.md").write_text(
        f"---\nname: {dirname}\ndescription: Usar cuando se pruebe el test.\n---\n", encoding="utf-8"
    )
    return skill_md


def _valid_fm(name: str) -> str:
    """Frontmatter valido completo (SDO + convenciones SWARMIND)."""
    return (
        f"name: {name}\n"
        "description: Usar cuando el usuario necesite validar documentos del test. "
        "documentos, validacion, tests.\n"
        "version: 1.0.0\n"
        "project_agnostic: true\n"
    )


# ===========================================================================
# _parse_frontmatter
# ===========================================================================


def test_parse_frontmatter_ok(tmp_path: Path) -> None:
    """Frontmatter bien formado -> dict con campos, sin error."""
    skill_md = _write_skill(tmp_path, "test-ok", _valid_fm("test-ok"))

    fm, err = vs._parse_frontmatter(skill_md.read_text(encoding="utf-8"))

    assert err is None
    assert fm["name"] == "test-ok"
    assert "description" in fm


def test_parse_frontmatter_sin_bloque(tmp_path: Path) -> None:
    """Archivo sin bloque --- -> error 'frontmatter faltante'."""
    skill_dir = tmp_path / "nofm"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("# Solo markdown\n", encoding="utf-8")

    fm, err = vs._parse_frontmatter(skill_md.read_text(encoding="utf-8"))

    assert fm == {}
    assert "frontmatter" in (err or "")


# ===========================================================================
# _validate_skill
# ===========================================================================


def test_skill_valido_sin_errores(tmp_path: Path) -> None:
    """Skill completo (SDO + version + project_agnostic + min.md) -> 0 errores."""
    skill_md = _write_skill(tmp_path, "test-ok", _valid_fm("test-ok"))

    errors = vs._validate_skill(skill_md.parent, quiet=True)

    assert errors == []


def test_skill_sin_version_error(tmp_path: Path) -> None:
    """Falta campo 'version' -> error (convencion SWARMIND)."""
    skill_md = _write_skill(
        tmp_path,
        "test-nov",
        "name: test-nov\n"
        "description: Usar cuando el usuario necesite validar documentos del test.\n"
        "project_agnostic: true\n",
    )

    errors = vs._validate_skill(skill_md.parent, quiet=True)

    assert any("version" in e for e in errors)


def test_skill_sin_project_agnostic_error(tmp_path: Path) -> None:
    """Falta campo 'project_agnostic' -> error (convencion SWARMIND)."""
    skill_md = _write_skill(
        tmp_path,
        "test-nopa",
        "name: test-nopa\n"
        "description: Usar cuando el usuario necesite validar documentos del test.\n"
        "version: 1.0.0\n",
    )

    errors = vs._validate_skill(skill_md.parent, quiet=True)

    assert any("project_agnostic" in e for e in errors)


def test_skill_sin_min_md_error(tmp_path: Path) -> None:
    """Falta SKILL.min.md -> error (convencion SWARMIND progressive disclosure)."""
    skill_md = _write_skill(tmp_path, "test-nomin", _valid_fm("test-nomin"))
    (skill_md.parent / "SKILL.min.md").unlink()

    errors = vs._validate_skill(skill_md.parent, quiet=True)

    assert any("SKILL.min.md" in e for e in errors)


def test_skill_description_no_sdo_error(tmp_path: Path) -> None:
    """description que no empieza con 'Usar cuando' -> error SDO (ADR-0047)."""
    skill_md = _write_skill(
        tmp_path,
        "test-nosdo",
        "name: test-nosdo\n"
        "description: Analiza documentos y genera resumenes legales del test.\n"
        "version: 1.0.0\n"
        "project_agnostic: true\n",
    )

    errors = vs._validate_skill(skill_md.parent, quiet=True)

    assert any("Usar cuando" in e for e in errors)


def test_skill_name_no_coincide_directorio_error(tmp_path: Path) -> None:
    """frontmatter name != directorio -> error."""
    skill_md = _write_skill(tmp_path, "test-dir", _valid_fm("test-otro"))

    errors = vs._validate_skill(skill_md.parent, quiet=True)

    assert any("directorio" in e for e in errors)


def test_skill_referencia_rota_error(tmp_path: Path) -> None:
    """Referencia a references/inexistente en el body -> error."""
    skill_md = _write_skill(tmp_path, "test-ref", _valid_fm("test-ref"))
    body = skill_md.read_text(encoding="utf-8") + "\nVer references/type-foo.md\n"
    skill_md.write_text(body, encoding="utf-8")

    errors = vs._validate_skill(skill_md.parent, quiet=True)

    assert any("references/type-foo.md" in e for e in errors)


def test_skill_nombre_invalido_error(tmp_path: Path) -> None:
    """name con mayusculas -> error de formato spec."""
    skill_md = _write_skill(
        tmp_path,
        "test-may",
        "name: Test-Mayusculas\n"
        "description: Usar cuando el usuario necesite validar documentos del test.\n"
        "version: 1.0.0\n"
        "project_agnostic: true\n",
    )

    errors = vs._validate_skill(skill_md.parent, quiet=True)

    assert any("invalido" in e for e in errors)


# ===========================================================================
# References muertas (progressive disclosure, ADR-0047)
# ===========================================================================


def test_references_muertas_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """references/ con archivo nunca enlazado en SKILL.md -> warning (no error)."""
    skill_md = _write_skill(tmp_path, "test-dead", _valid_fm("test-dead"))
    (skill_md.parent / "references").mkdir()
    (skill_md.parent / "references" / "type-foo.md").write_text("# Foo\n", encoding="utf-8")
    (skill_md.parent / "references" / "type-bar.md").write_text("# Bar\n", encoding="utf-8")
    body = skill_md.read_text(encoding="utf-8") + "\nVer references/type-foo.md\n"
    skill_md.write_text(body, encoding="utf-8")

    errors = vs._validate_skill(skill_md.parent, quiet=False)
    out = capsys.readouterr().out

    assert errors == []  # no es error, es warning
    assert "type-bar.md" in out  # la no referenciada aparece
    assert "type-foo.md" not in out  # la referenciada NO es dead


def test_references_todas_enlazadas_sin_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Todas las references/ enlazadas -> sin warning de muertas."""
    skill_md = _write_skill(tmp_path, "test-nod", _valid_fm("test-nod"))
    (skill_md.parent / "references").mkdir()
    (skill_md.parent / "references" / "type-foo.md").write_text("# Foo\n", encoding="utf-8")
    body = skill_md.read_text(encoding="utf-8") + "\nVer references/type-foo.md\n"
    skill_md.write_text(body, encoding="utf-8")

    vs._validate_skill(skill_md.parent, quiet=False)
    out = capsys.readouterr().out

    assert "no referenciadas" not in out


# ===========================================================================
# Frontmatter spec completo (agentskills.io: license/compatibility)
# ===========================================================================


def test_license_ausente_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Falta license -> warning (spec: opcional recomendado), no error."""
    skill_md = _write_skill(
        tmp_path,
        "test-lic",
        "name: test-lic\n"
        "description: Usar cuando el usuario necesite validar documentos del test.\n"
        "version: 1.0.0\n"
        "project_agnostic: true\n",
    )

    errors = vs._validate_skill(skill_md.parent, quiet=False)
    out = capsys.readouterr().out

    assert errors == []
    assert "license" in out


def test_compatibility_requerido_con_scripts_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Skill con scripts/ pero sin compatibility -> warning (spec: requisitos de entorno)."""
    skill_md = _write_skill(tmp_path, "test-compat", _valid_fm("test-compat"))
    (skill_md.parent / "scripts").mkdir()
    (skill_md.parent / "scripts" / "run.py").write_text("# script\n", encoding="utf-8")

    vs._validate_skill(skill_md.parent, quiet=False)
    out = capsys.readouterr().out

    assert "compatibility" in out


def test_compatibility_presente_sin_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Skill con scripts/ Y compatibility -> sin warning."""
    skill_md = _write_skill(tmp_path, "test-compat-ok", _valid_fm("test-compat-ok"))
    (skill_md.parent / "scripts").mkdir()
    (skill_md.parent / "scripts" / "run.py").write_text("# script\n", encoding="utf-8")
    t = skill_md.read_text(encoding="utf-8")
    t = t.replace("project_agnostic: true\n", "project_agnostic: true\ncompatibility: Python 3.12+\n", 1)
    skill_md.write_text(t, encoding="utf-8")

    vs._validate_skill(skill_md.parent, quiet=False)
    out = capsys.readouterr().out

    assert "compatibility" not in out


# ===========================================================================
# _validate_registry
# ===========================================================================


def test_registry_sincronizado_con_disco(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Registry lista los mismos skills que el directorio -> 0 errores."""
    for name in ("skill-a", "skill-b"):
        (tmp_path / name).mkdir(parents=True)
        (tmp_path / name / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Usar cuando el usuario pruebe el registro.\n---\n",
            encoding="utf-8",
        )
    registry = tmp_path / "skills_registry.yaml"
    registry.write_text(
        "skills:\n"
        "  - name: skill-a\n"
        "    domain: test\n"
        "    description: Usar cuando el usuario pruebe el registro.\n"
        "    version: 1.0.0\n"
        "    project_agnostic: true\n"
        "  - name: skill-b\n"
        "    domain: test\n"
        "    description: Usar cuando el usuario pruebe el registro.\n"
        "    version: 1.0.0\n"
        "    project_agnostic: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(vs, "_SKILLS_DIR", tmp_path)
    monkeypatch.setattr(vs, "_REGISTRY", registry)

    errors = vs._validate_registry(quiet=True)

    assert errors == []


def test_registry_falta_skill_en_disco(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Registry no lista un skill que existe en disco -> error."""
    (tmp_path / "skill-a").mkdir(parents=True)
    (tmp_path / "skill-a" / "SKILL.md").write_text(
        "---\nname: skill-a\ndescription: Usar cuando el usuario pruebe el registro.\n---\n",
        encoding="utf-8",
    )
    registry = tmp_path / "skills_registry.yaml"
    registry.write_text(
        "skills:\n"
        "  - name: skill-a\n"
        "    domain: test\n"
        "    description: Usar cuando el usuario pruebe el registro.\n"
        "    version: 1.0.0\n"
        "    project_agnostic: true\n"
        "  - name: skill-b\n"
        "    domain: test\n"
        "    description: Usar cuando el usuario pruebe el registro.\n"
        "    version: 1.0.0\n"
        "    project_agnostic: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(vs, "_SKILLS_DIR", tmp_path)
    monkeypatch.setattr(vs, "_REGISTRY", registry)

    errors = vs._validate_registry(quiet=True)

    assert any("skill-b" in e for e in errors)


# ===========================================================================
# Integracion: skills reales del repo
# ===========================================================================def test_todos_los_skills_reales_validos() -> None:
    """Los 33 skills reales de .opencode/skills pasan el validador sin errores."""
    skills_dir = Path(__file__).resolve().parents[2] / ".opencode" / "skills"
    if not skills_dir.is_dir():
        pytest.skip("directorio de skills no disponible")

    all_errors: list[str] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name == "__pycache__":
            continue
        errors = vs._validate_skill(skill_dir, quiet=True)
        all_errors.extend(errors)

    assert all_errors == [], f"Errores en skills reales: {all_errors}"


# ===========================================================================
# main / CLI
# ===========================================================================


def test_main_strict_exit_cero(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """--strict sobre los skills reales -> sin SystemExit y 'validos' en output."""
    skills_dir = Path(__file__).resolve().parents[2] / ".opencode" / "skills"
    if not skills_dir.is_dir():
        pytest.skip("directorio de skills no disponible")

    monkeypatch.setattr(vs, "_SKILLS_DIR", skills_dir)
    monkeypatch.setattr(vs, "_REGISTRY", skills_dir / "skills_registry.yaml")
    monkeypatch.setattr(sys, "argv", ["validate_skills.py", "--strict", "--quiet"])
    vs.main()  # no debe lanzar SystemExit si todo es valido

    out = capsys.readouterr().out
    assert "Todos los skills validos" in out


def test_main_strict_errores_exit_1(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """--strict con un skill invalido -> SystemExit(1)."""
    skills_dir = Path(__file__).resolve().parents[2] / ".opencode" / "skills"
    if not skills_dir.is_dir():
        pytest.skip("directorio de skills no disponible")

    # Monkeypatch de _SKILLS_DIR a un dir con un skill invalido
    bad_root = Path(__file__).parent / "_tmp_bad_skills"
    (bad_root / "bad-skill").mkdir(parents=True, exist_ok=True)
    (bad_root / "bad-skill" / "SKILL.md").write_text(
        "---\nname: bad-skill\ndescription: sin prefijo SDO.\n---\n", encoding="utf-8"
    )
    (bad_root / "bad-skill" / "SKILL.min.md").write_text("---\nname: bad-skill\n---\n", encoding="utf-8")
    bad_registry = bad_root / "skills_registry.yaml"
    bad_registry.write_text("skills:\n  - name: bad-skill\n", encoding="utf-8")

    monkeypatch.setattr(vs, "_SKILLS_DIR", bad_root)
    monkeypatch.setattr(vs, "_REGISTRY", bad_registry)
    monkeypatch.setattr(sys, "argv", ["validate_skills.py", "--strict", "--quiet"])
    with pytest.raises(SystemExit) as exc:
        vs.main()

    assert exc.value.code == 1
