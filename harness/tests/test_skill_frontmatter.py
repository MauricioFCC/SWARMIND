"""
Tests TDD para SkillFrontmatterValidator — validador del estandar agentskills.io (L1).

Cubre:
  - Skill valido completo (name==dirname, description accionable, license,
    compatibility, metadata) -> valid=True, 0 errors
  - name que no matchea la regex (mayusculas/espacios) -> error
  - name != dirname -> error
  - description ausente -> error
  - description > 1024 chars -> error
  - description corta -> warning (no error)
  - description sin verbo accionable -> warning
  - frontmatter roto (YAML invalido) -> error
  - sin frontmatter -> error
  - archivo no existe -> error
  - compatibility como lista -> valido
  - metadata no-dict -> error
  - allowed-tools como list -> valido; como string -> error
  - validate_directory: name != dirname -> error; sin references/scripts -> warning
  - validate_all recorre y ordena
  - report.summary() no vacio y contiene "valid" o "invalid"
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.memory_rag.skill_frontmatter import (
    MAX_DESCRIPTION_LEN,
    SDO_PREFIX,
    SKILL_NAME_RE,
    SkillFrontmatterValidator,
    SkillReport,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _write_skill(root: Path, dirname: str, frontmatter: str) -> Path:
    """Escribe un skill de prueba y retorna la ruta a su SKILL.md."""
    skill_dir = root / dirname
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(f"---\n{frontmatter}---\n\n# Skill de prueba\n", encoding="utf-8")
    return skill_md


def _valid_frontmatter(name: str) -> str:
    """Frontmatter de un skill valido completo (name == dirname, SDO)."""
    return (
        f"name: {name}\n"
        "description: Usar cuando se necesite revisar o extraer informacion de textos legales. "
        "documentos, resumenes, contratos.\n"
        "license: MIT\n"
        "compatibility: Python 3.12+\n"
        "metadata:\n"
        "  author: test-author\n"
        "  version: 1.0.0\n"
    )


@pytest.fixture
def validator() -> SkillFrontmatterValidator:
    """Validador aislado por test."""
    return SkillFrontmatterValidator()


# ===========================================================================
# validate_file — skill valido
# ===========================================================================


def test_valida_skill_completo_valido(tmp_path: Path, validator: SkillFrontmatterValidator) -> None:
    """Un skill con todos los campos recomendados y name==dirname es valido sin errores."""
    skill_md = _write_skill(tmp_path, "test-skill", _valid_frontmatter("test-skill"))

    report = validator.validate_file(skill_md)

    assert report.valid is True
    assert report.errors == ()
    assert report.warnings == ()
    assert report.skill_name == "test-skill"


# ===========================================================================
# validate_file — name
# ===========================================================================


def test_name_no_matchea_regex_error(tmp_path: Path, validator: SkillFrontmatterValidator) -> None:
    """name con mayusculas/espacios no matchea la regex -> error."""
    skill_md = _write_skill(
        tmp_path,
        "badname-skill",
        "name: Test Skill\n"
        "description: Analiza documentos y genera resumenes legales para el test.\n",
    )

    report = validator.validate_file(skill_md)

    assert report.valid is False
    assert any("name_invalido" in error for error in report.errors)


def test_name_no_coincide_con_directorio_error(
    tmp_path: Path, validator: SkillFrontmatterValidator
) -> None:
    """name valido pero distinto al directorio padre -> error."""
    skill_md = _write_skill(
        tmp_path,
        "my-skill",
        "name: other-skill\n"
        "description: Analiza documentos y genera resumenes legales para el test.\n",
    )

    report = validator.validate_file(skill_md)

    assert report.valid is False
    assert any("name_no_coincide_con_directorio" in error for error in report.errors)


# ===========================================================================
# validate_file — description
# ===========================================================================


def test_description_ausente_error(tmp_path: Path, validator: SkillFrontmatterValidator) -> None:
    """Sin campo description -> error."""
    skill_md = _write_skill(tmp_path, "nodesc-skill", "name: nodesc-skill\nlicense: MIT\n")

    report = validator.validate_file(skill_md)

    assert report.valid is False
    assert any("description_ausente" in error for error in report.errors)


def test_description_mas_1024_error(tmp_path: Path, validator: SkillFrontmatterValidator) -> None:
    """description mayor a MAX_DESCRIPTION_LEN -> error."""
    descripcion_larga = "analiza " * (MAX_DESCRIPTION_LEN + 1)
    skill_md = _write_skill(
        tmp_path,
        "longdesc-skill",
        f"name: longdesc-skill\n" f"description: {descripcion_larga}\n",
    )

    report = validator.validate_file(skill_md)

    assert report.valid is False
    assert any("description_demasiado_larga" in error for error in report.errors)


def test_description_corta_warning(tmp_path: Path, validator: SkillFrontmatterValidator) -> None:
    """description menor a MIN_DESCRIPTION_LEN -> warning, no error."""
    skill_md = _write_skill(tmp_path, "corto-skill", "name: corto-skill\ndescription: Analiza\n")

    report = validator.validate_file(skill_md)

    assert report.valid is True
    assert report.errors == ()
    assert any("description_corta" in warning for warning in report.warnings)


def test_description_sin_verbo_accionable_warning(
    tmp_path: Path, validator: SkillFrontmatterValidator
) -> None:
    """description sin verbo accionable -> warning, no error."""
    skill_md = _write_skill(
        tmp_path,
        "sinverbo-skill",
        "name: sinverbo-skill\n"
        "description: Ayuda con documentos legales y su gestion diaria.\n",
    )

    report = validator.validate_file(skill_md)

    assert report.valid is True
    assert report.errors == ()
    assert any("description_sin_verbo" in warning for warning in report.warnings)


# ===========================================================================
# validate_file — frontmatter / archivo
# ===========================================================================


def test_frontmatter_roto_yaml_invalido_error(
    tmp_path: Path, validator: SkillFrontmatterValidator
) -> None:
    """YAML roto dentro del frontmatter -> error claro."""
    skill_md = _write_skill(
        tmp_path,
        "rotoskill",
        "name: [no_cerrado\n" "description: Analiza documentos legales del test.\n",
    )

    report = validator.validate_file(skill_md)

    assert report.valid is False
    assert any("frontmatter_invalido" in error for error in report.errors)


def test_sin_frontmatter_error(tmp_path: Path, validator: SkillFrontmatterValidator) -> None:
    """Archivo sin bloque frontmatter --- -> error."""
    skill_dir = tmp_path / "nofm-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("# Solo markdown\n\nsin frontmatter\n", encoding="utf-8")

    report = validator.validate_file(skill_md)

    assert report.valid is False
    assert any("frontmatter_ausente" in error for error in report.errors)


def test_archivo_no_existe_error(tmp_path: Path, validator: SkillFrontmatterValidator) -> None:
    """SKILL.md inexistente -> error archivo_no_encontrado."""
    report = validator.validate_file(tmp_path / "no-skill" / "SKILL.md")

    assert report.valid is False
    assert any("archivo_no_encontrado" in error for error in report.errors)


# ===========================================================================
# validate_file — campos opcionales
# ===========================================================================


def test_compatibility_como_lista_valido(
    tmp_path: Path, validator: SkillFrontmatterValidator
) -> None:
    """compatibility puede ser una lista de strings -> valido."""
    skill_md = _write_skill(
        tmp_path,
        "compat-skill",
        "name: compat-skill\n"
        "description: Analiza la compatibilidad en lista de herramientas del test.\n"
        "compatibility:\n"
        "  - Python 3.12+\n"
        "  - uv\n",
    )

    report = validator.validate_file(skill_md)

    assert report.valid is True
    assert report.errors == ()


def test_metadata_no_dict_error(tmp_path: Path, validator: SkillFrontmatterValidator) -> None:
    """metadata debe ser un mapa string->string -> error si es otro tipo."""
    skill_md = _write_skill(
        tmp_path,
        "metas-skill",
        "name: metas-skill\n"
        "description: Analiza y valida documentos de ejemplo para el test de metadata.\n"
        "metadata: no-es-un-mapa\n",
    )

    report = validator.validate_file(skill_md)

    assert report.valid is False
    assert any("metadata_tipo_invalido" in error for error in report.errors)


def test_allowed_tools_como_lista_valido(
    tmp_path: Path, validator: SkillFrontmatterValidator
) -> None:
    """allowed-tools como lista de strings -> valido."""
    skill_md = _write_skill(
        tmp_path,
        "tools-skill",
        "name: tools-skill\n"
        "description: Analiza herramientas permitidas para validar el tipo de allowed-tools.\n"
        "allowed-tools:\n"
        "  - Bash(git:*)\n"
        "  - Read\n",
    )

    report = validator.validate_file(skill_md)

    assert report.valid is True
    assert report.errors == ()


def test_allowed_tools_como_string_error(
    tmp_path: Path, validator: SkillFrontmatterValidator
) -> None:
    """allowed-tools como string -> error (debe ser lista)."""
    skill_md = _write_skill(
        tmp_path,
        "toolsstr-skill",
        "name: toolsstr-skill\n"
        "description: Analiza herramientas permitidas para validar el tipo de allowed-tools.\n"
        'allowed-tools: "Bash(git:*)"\n',
    )

    report = validator.validate_file(skill_md)

    assert report.valid is False
    assert any("allowed_tools_tipo_invalido" in error for error in report.errors)


# ===========================================================================
# validate_directory
# ===========================================================================


def test_validate_directory_name_no_coincide_error(
    tmp_path: Path, validator: SkillFrontmatterValidator
) -> None:
    """validate_directory detecta name != dirname -> error."""
    skill_md = _write_skill(
        tmp_path,
        "my-skill",
        "name: other-skill\n"
        "description: Analiza documentos y genera resumenes legales para el test.\n",
    )

    report = validator.validate_directory(skill_md.parent)

    assert report.valid is False
    assert any("name_no_coincide_con_directorio" in error for error in report.errors)


def test_validate_directory_sin_references_scripts_warning(
    tmp_path: Path, validator: SkillFrontmatterValidator
) -> None:
    """Faltan directories opcionales references/ y scripts/ -> warning, no error."""
    skill_md = _write_skill(tmp_path, "struct-skill", _valid_frontmatter("struct-skill"))

    report = validator.validate_directory(skill_md.parent)

    assert report.valid is True
    assert report.errors == ()
    assert any("references_ausente" in warning for warning in report.warnings)
    assert any("scripts_ausente" in warning for warning in report.warnings)


# ===========================================================================
# validate_all
# ===========================================================================


def test_validate_all_recorre_y_ordena(
    tmp_path: Path, validator: SkillFrontmatterValidator
) -> None:
    """validate_all recorre skills_root/*/SKILL.md y devuelve reports ordenados por nombre."""
    _write_skill(tmp_path, "bbb-skill", _valid_frontmatter("bbb-skill"))
    _write_skill(tmp_path, "aaa-skill", _valid_frontmatter("aaa-skill"))

    reports = validator.validate_all(tmp_path)

    assert len(reports) == 2
    assert [report.skill_name for report in reports] == ["aaa-skill", "bbb-skill"]
    assert all(report.valid for report in reports)


# ===========================================================================
# SkillReport.summary
# ===========================================================================


def test_summary_no_vacio_contiene_valid(
    tmp_path: Path, validator: SkillFrontmatterValidator
) -> None:
    """summary() devuelve una linea legible con 'valid' o 'invalid'."""
    skill_md = _write_skill(tmp_path, "summ-skill", _valid_frontmatter("summ-skill"))

    report = validator.validate_file(skill_md)
    summary = report.summary()

    assert summary.strip() != ""
    assert ("valid" in summary) or ("invalid" in summary)


# ===========================================================================
# SDO — Skill Discovery Optimization (ADR-0047)
# ===========================================================================


def test_description_sin_sdo_warning(tmp_path: Path, validator: SkillFrontmatterValidator) -> None:
    """description que NO empieza con 'Usar cuando' -> warning description_sin_sdo."""
    skill_md = _write_skill(
        tmp_path,
        "nosdo-skill",
        "name: nosdo-skill\n"
        "description: Analiza documentos y genera resumenes legales del test.\n",
    )

    report = validator.validate_file(skill_md)

    assert report.valid is True
    assert report.errors == ()
    assert any("description_sin_sdo" in warning for warning in report.warnings)


def test_description_con_sdo_no_warning(tmp_path: Path, validator: SkillFrontmatterValidator) -> None:
    """description que empieza con 'Usar cuando' -> sin warning SDO."""
    skill_md = _write_skill(tmp_path, "sdo-skill", _valid_frontmatter("sdo-skill"))

    report = validator.validate_file(skill_md)

    assert report.valid is True
    assert report.errors == ()
    assert not any("description_sin_sdo" in warning for warning in report.warnings)


def test_description_con_sdo_case_insensitive(tmp_path: Path, validator: SkillFrontmatterValidator) -> None:
    """El prefijo SDO se detecta case-insensitive ('USAR CUANDO...' tambien vale)."""
    skill_md = _write_skill(
        tmp_path,
        "sdomay-skill",
        "name: sdomay-skill\n"
        "description: USAR CUANDO el usuario necesite analizar datos de ejemplo.\n",
    )

    report = validator.validate_file(skill_md)

    assert report.valid is True
    assert not any("description_sin_sdo" in warning for warning in report.warnings)


def test_sdo_prefix_constante() -> None:
    """SDO_PREFIX es 'usar cuando' (patron superpowers 2026)."""
    assert SDO_PREFIX == "usar cuando"


def test_validar_todos_los_skills_reales_sdo() -> None:
    """Los 33 skills reales del repo cumplen SDO (integracion con validate_skills.py)."""
    from pathlib import Path

    import scripts.validate_skills  # noqa: F401  # importable

    skills_dir = Path(__file__).resolve().parents[2] / ".opencode" / "skills"
    if not skills_dir.is_dir():
        pytest.skip("directorio de skills no disponible")
    validator = SkillFrontmatterValidator()
    reports = validator.validate_all(skills_dir)
    assert len(reports) >= 30
    for report in reports:
        assert not any("description_sin_sdo" in w for w in report.warnings), (
            f"{report.skill_name}: description sin prefijo SDO"
        )


# ===========================================================================
# Constantes
# ===========================================================================


def test_constantes_y_regex_publicas() -> None:
    """Las constantes publicas estan disponibles y la regex compila."""
    assert SKILL_NAME_RE.match("pdf-processing") is not None
    assert SKILL_NAME_RE.match("PDF-Processing") is None
    assert SKILL_NAME_RE.match("") is None
    assert len(SKILL_NAME_RE.pattern) > 0


def test_skill_report_es_dataclass_frozen() -> None:
    """SkillReport es un dataclass frozen inmutable."""
    report = SkillReport(
        skill_name="demo",
        path="C:/demo/SKILL.md",
        valid=True,
        errors=(),
        warnings=("license_ausente",),
        frontmatter={"name": "demo"},
    )
    assert report.valid is True
    assert report.warnings == ("license_ausente",)
