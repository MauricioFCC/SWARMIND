"""Tests de integridad de principios (SDD + TDD adversarial/mutante).

Verifica los invariantes de "integridad de principios" del harness:

1. Herencia referencial de skills: toda ruta declarada en ``inherit:`` de un
   ``SKILL.md`` existe bajo ``.opencode/`` (reutiliza el resolver
   :mod:`harness.context.skill_inherit`; ``IDP``: no se reimplementa; si el
   resolver no existiera, se usa un parser propio).
2. Coherencia de version: ``base_principles_full.md`` declara la misma
   ``version`` que ``base_principles.md`` (anti-drift de las copias N1/N3).
3. Cero token N1 obsoleto: ninguna copia (base/min/full) reintroduce
   ``SEG: 0 secrets | validate input`` (token promovido a ``VAL``).
4. ADR formal: ``docs/adr/adr-0098-*.md`` expone Status/Date/Contexto/
   Decision/Consecuencias.
5. Anti-drift N1: el conjunto de codigos N1 de full == base == min.

Incluye asserts mutation-style que demuestran el poder discriminante de los
checkers (matan al mutante que borra una linea N1, rompe un ``inherit`` o
desincroniza una version). ``mutmut`` no es viable en Windows nativo (requiere
WSL); ver ``specs/principles-integrity.md`` seccion "Verificacion y mutation".

Contexto: los arreglos de produccion corren en paralelo; si aun no cierran,
los tests de integracion quedan en RED — estado esperado (``SPE``/``GATE``).
Esta suite es solo-lectura: no edita produccion ni usa red ni subprocess.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Rutas y constantes (MAG)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
OPENCODE_DIR = ROOT / ".opencode"
CORE_DIR = OPENCODE_DIR / "core"
SKILLS_DIR = OPENCODE_DIR / "skills"
BASE_PRINCIPLES = CORE_DIR / "base_principles.md"
MIN_PRINCIPLES = CORE_DIR / "base_principles.min.md"
FULL_PRINCIPLES = CORE_DIR / "base_principles_full.md"
ADR_DIR = ROOT / "docs" / "adr"
ADR0098_GLOB = "adr-0098-*.md"

#: Fragmento del token N1 obsoleto que debio migrarse de SEG a VAL.
STALE_SEG_N1_FRAGMENT = "validate input"

#: Codigo N1 sembrado en los asserts mutation-style.
N1_CODE_FOR_MUTATION = "VAL"

#: Nombre canonico del archivo de skill.
SKILL_MD_FILENAME = "SKILL.md"

_CODE_LINE_RE = re.compile(r"^([A-Z][A-Z0-9]{1,4}):")
_VERSION_RE = re.compile(r"^version:\s*([0-9]+(?:\.[0-9]+)*)", re.MULTILINE)

#: Secciones minimas de un ADR formal (Nombre -> patron de linea).
ADR_REQUIRED_SECTIONS: tuple[tuple[str, str], ...] = (
    ("Status", r"(?im)^\s*(?:[-*]\s+|#{1,6}\s+)?(?:\*\*)?\s*status\b"),
    ("Date", r"(?im)^\s*(?:[-*]\s+|#{1,6}\s+)?(?:\*\*)?\s*date\b"),
    ("Contexto", r"(?im)^\s*(?:[-*]\s+|#{1,6}\s+)?(?:\*\*)?\s*contexto\b"),
    ("Decision", r"(?im)^\s*(?:[-*]\s+|#{1,6}\s+)?(?:\*\*)?\s*decisi[o\u00f3]n\b"),
    ("Consecuencias", r"(?im)^\s*(?:[-*]\s+|#{1,6}\s+)?(?:\*\*)?\s*consecuencias\b"),
)

#: Reutiliza el resolver de herencia si existe (IDP); si no, usa fallback propio.
try:
    from harness.context import skill_inherit as _inherit_resolver

    _HAS_INHERIT_RESOLVER = True
except ImportError:  # pragma: no cover - defensivo segun disponibilidad del modulo
    _HAS_INHERIT_RESOLVER = False


# ---------------------------------------------------------------------------
# Helpers (checkers puros; reutilizados por los asserts mutation-style)
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    """Lee un archivo de texto en UTF-8.

    Args:
        path: Ruta del archivo.

    Returns:
        Contenido del archivo.

    Raises:
        AssertionError: Si el archivo no existe.
    """
    assert path.is_file(), f"Archivo no encontrado: {path}"
    return path.read_text(encoding="utf-8")


def _extract_first_fenced_block(text: str) -> str:
    """Extrae el primer bloque cercado (``` ... ```) de un Markdown.

    En las tres copias de principios el primer bloque cercado es el N1.

    Args:
        text: Contenido Markdown.

    Returns:
        Cuerpo del bloque, sin las vallas.

    Raises:
        AssertionError: Si no hay bloque cercado o falta el cierre.
    """
    start = text.find("```")
    assert start != -1, "No se encontro bloque cercado (```)"
    first_newline = text.find("\n", start)
    end = text.find("```", first_newline)
    assert end != -1, "Bloque cercado sin cierre (```)"
    return text[first_newline + 1 : end]


def _n1_codes(text: str) -> set[str]:
    """Extrae el conjunto de codigos N1 del primer bloque cercado.

    Args:
        text: Contenido de un archivo de principios.

    Returns:
        Conjunto de codigos (p.ej. ``{"RSF", "VAL", "ATM"}``).
    """
    block = _extract_first_fenced_block(text)
    codes: set[str] = set()
    for line in block.splitlines():
        match = _CODE_LINE_RE.match(line.strip())
        if match:
            codes.add(match.group(1))
    return codes


def _assert_same_n1_codes(reference_text: str, other_text: str) -> None:
    """Verifica que dos archivos compartan el mismo conjunto de codigos N1.

    Args:
        reference_text: Texto de referencia.
        other_text: Texto a comparar.

    Raises:
        AssertionError: Si los conjuntos difieren (drift N1).
    """
    reference = _n1_codes(reference_text)
    other = _n1_codes(other_text)
    assert reference == other, (
        f"Drift N1: solo en referencia={sorted(reference - other)}, "
        f"solo en comparado={sorted(other - reference)}"
    )


def _assert_n1_no_extra(reference_text: str, other_text: str) -> None:
    """Verifica que un archivo no reintroduzca codigos N1 ajenos.

    En la SSOT ``base_principles.md`` viven todos los codigos N1; las
    copias (``min``/``full``) no deben introducir un N1 distinto.

    Args:
        reference_text: Texto de referencia (SSOT de N1).
        other_text: Texto a comparar.

    Raises:
        AssertionError: Si ``other_text`` contiene codigos N1 que no estan
            en la referencia (reintroduccion de un N1 distinto).
    """
    reference = _n1_codes(reference_text)
    extra = sorted(_n1_codes(other_text) - reference)
    assert not extra, f"N1 distinto reintroducido (ajeno a la SSOT): {extra}"


def _frontmatter_version(text: str) -> tuple[int, ...]:
    """Extrae y normaliza la ``version`` del frontmatter YAML.

    Args:
        text: Contenido Markdown con frontmatter.

    Returns:
        Tupla ``(major, minor, patch)``.

    Raises:
        AssertionError: Si el frontmatter no declara ``version``.
    """
    match = _VERSION_RE.search(text)
    assert match is not None, "Frontmatter sin campo 'version'"
    parts = [int(part) for part in match.group(1).split(".")]
    return tuple((parts + [0, 0, 0])[:3])


def _assert_same_version(reference_text: str, other_text: str) -> None:
    """Verifica que dos archivos declaren la misma version de frontmatter.

    Args:
        reference_text: Texto de referencia.
        other_text: Texto a comparar.

    Raises:
        AssertionError: Si las versiones difieren (drift de version).
    """
    reference = _frontmatter_version(reference_text)
    other = _frontmatter_version(other_text)
    assert other == reference, f"Drift version: {other} != {reference}"


def _stale_seg_lines(text: str) -> list[str]:
    """Devuelve las lineas N1 ``SEG:`` que aun contienen el token obsoleto.

    Args:
        text: Contenido de un archivo de principios.

    Returns:
        Lista de lineas ofensoras (vacia si no hay drift).
    """
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("SEG:") and STALE_SEG_N1_FRAGMENT in line
    ]


def _missing_adr_sections(text: str) -> list[str]:
    """Devuelve las secciones obligatorias ausentes en un ADR.

    Args:
        text: Contenido del ADR.

    Returns:
        Lista de nombres de seccion ausentes (vacia si es formal).
    """
    return [
        name
        for name, pattern in ADR_REQUIRED_SECTIONS
        if re.search(pattern, text) is None
    ]


def _remove_n1_line(text: str, code: str) -> str:
    """Elimina (mutacion) la linea N1 de un codigo dado.

    Args:
        text: Contenido de un archivo de principios.
        code: Codigo cuya linea se elimina (p.ej. ``VAL``).

    Returns:
        Texto mutado sin la linea ``<code>:``.
    """
    prefix = f"{code}:"
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith(prefix)
    )


def _parse_inherit_fallback(skill_md: Path) -> tuple[str, ...]:
    """Parser propio de ``inherit:`` (fallback si no hay resolver disponible).

    Args:
        skill_md: Ruta del SKILL.md.

    Returns:
        Tupla de rutas relativas declaradas bajo ``inherit:``.
    """
    lines = skill_md.read_text(encoding="utf-8-sig").splitlines()
    paths: list[str] = []
    in_block = False
    for line in lines:
        if line.startswith("inherit:"):
            in_block = True
            continue
        if in_block:
            if line.startswith("  - "):
                paths.append(line.strip()[2:].strip())
            elif line.strip():
                break
    return tuple(paths)


def _inherit_paths(skill_md: Path) -> tuple[str, ...]:
    """Extrae las rutas ``inherit:`` usando el resolver, o un parser propio.

    Args:
        skill_md: Ruta del SKILL.md.

    Returns:
        Tupla de rutas relativas declaradas en el frontmatter.
    """
    if _HAS_INHERIT_RESOLVER:
        return _inherit_resolver.parse_inherit(skill_md)
    return _parse_inherit_fallback(skill_md)


def _inherit_corpus_errors(skills_dir: Path, base_dir: Path) -> list[str]:
    """Valida la integridad referencial de ``inherit:`` de un corpus de skills.

    Args:
        skills_dir: Raiz del corpus (cada skill en su subdirectorio).
        base_dir: Raiz contra la que se resuelven las rutas heredadas.

    Returns:
        Lista de errores WHAT+WHY+WHERE (vacia si todas las rutas resuelven).
    """
    if _HAS_INHERIT_RESOLVER:
        return _inherit_resolver.validate_inherit_corpus(skills_dir, base_dir)
    errors: list[str] = []
    for skill_md in sorted(skills_dir.glob(f"**/{SKILL_MD_FILENAME}")):
        for rel_path in _parse_inherit_fallback(skill_md):
            candidate = (base_dir / rel_path).resolve()
            if not candidate.is_file():
                errors.append(
                    f"WHAT: artefacto heredado ausente '{rel_path}' en {skill_md}. "
                    "WHY: el frontmatter declara 'inherit:' sin archivo destino. "
                    "WHERE: _inherit_corpus_errors"
                )
    return errors


# ---------------------------------------------------------------------------
# Invariantes de integridad
# ---------------------------------------------------------------------------


def test_all_skills_inherit_paths_exist() -> None:
    """Toda ruta ``inherit:`` de todo ``SKILL.md`` existe bajo ``.opencode/``."""
    # Arrange
    skill_files = sorted(SKILLS_DIR.glob(f"**/{SKILL_MD_FILENAME}"))
    assert skill_files, f"No se encontraron {SKILL_MD_FILENAME} en {SKILLS_DIR}"

    # Act
    errors = _inherit_corpus_errors(SKILLS_DIR, OPENCODE_DIR)
    declared = [
        (skill_md, rel_path)
        for skill_md in skill_files
        for rel_path in _inherit_paths(skill_md)
    ]

    # Assert
    assert declared, "Ninguna skill declara 'inherit:' (checker vacuo)"
    assert errors == [], "Herencia referencial rota:\n" + "\n".join(errors)
    missing = [rel for _skill, rel in declared if not (OPENCODE_DIR / rel).is_file()]
    assert not missing, f"Rutas 'inherit:' inexistentes bajo .opencode/: {missing}"


def test_full_and_base_versions_consistent() -> None:
    """``_full.md`` declara la misma ``version`` que ``base_principles.md``."""
    # Arrange
    base_text = _read(BASE_PRINCIPLES)
    full_text = _read(FULL_PRINCIPLES)
    min_text = _read(MIN_PRINCIPLES)

    # Act / Assert
    _assert_same_version(base_text, full_text)
    _assert_same_version(base_text, min_text)


def test_no_stale_n1_anywhere() -> None:
    """Ninguna copia (base/min/full) conserva ``SEG: ... validate input``."""
    # Arrange
    copies = (BASE_PRINCIPLES, MIN_PRINCIPLES, FULL_PRINCIPLES)

    # Act
    offenders = {
        path.name: stale
        for path in copies
        if (stale := _stale_seg_lines(_read(path)))
    }

    # Assert
    assert not offenders, f"Token N1 obsoleto (SEG -> VAL) presente: {offenders}"


def test_adr0098_formal() -> None:
    """El ADR-0098 expone Status/Date/Contexto/Decision/Consecuencias."""
    # Arrange
    adrs = sorted(ADR_DIR.glob(ADR0098_GLOB))
    if not adrs:
        pytest.skip(f"ADR-0098 local-only ausente (gitignoreado): {ADR_DIR / ADR0098_GLOB}")

    # Act / Assert
    for adr in adrs:
        missing = _missing_adr_sections(_read(adr))
        assert not missing, f"{adr.name} no es ADR formal; faltan secciones: {missing}"


def test_no_duplicate_n1_across_files() -> None:
    """El set N1 de base == min y full no reintroduce un N1 distinto."""
    # Arrange
    base_text = _read(BASE_PRINCIPLES)
    min_text = _read(MIN_PRINCIPLES)
    full_text = _read(FULL_PRINCIPLES)

    # Act / Assert
    _assert_same_n1_codes(base_text, min_text)
    _assert_n1_no_extra(base_text, full_text)


# ---------------------------------------------------------------------------
# Mutation-style: demuestran que los checkers matan al mutante
# ---------------------------------------------------------------------------


def test_mutation_detects_removed_n1_line() -> None:
    """Mutation-style: quitar una linea N1 de ``min`` es detectado."""
    # Arrange
    base_text = _read(BASE_PRINCIPLES)
    mutated_min = _remove_n1_line(_read(MIN_PRINCIPLES), N1_CODE_FOR_MUTATION)

    # Act / Assert
    with pytest.raises(AssertionError, match=N1_CODE_FOR_MUTATION):
        _assert_same_n1_codes(base_text, mutated_min)


def test_mutation_rejects_broken_inherit_path(tmp_path: Path) -> None:
    """Mutation-style: un ``inherit:`` a path inexistente es rechazado."""
    # Arrange
    skill_dir = tmp_path / "skills" / "bad"
    skill_dir.mkdir(parents=True)
    (skill_dir / SKILL_MD_FILENAME).write_text(
        "---\nname: bad\ninherit:\n  - core/no-existe.md\n---\nbody\n",
        encoding="utf-8",
    )

    # Act
    errors = _inherit_corpus_errors(tmp_path / "skills", tmp_path)

    # Assert
    assert errors, "El validador acepto un 'inherit:' inexistente (mutante vivo)"
    assert any("WHAT" in error for error in errors), f"Errores sin WHAT: {errors}"


def test_mutation_detects_version_mismatch() -> None:
    """Mutation-style: una version desincronizada es detectada."""
    # Arrange
    reference = "---\nname: x\nversion: 3.5.0\n---\n"
    mutated = "---\nname: x\nversion: 2.7.0\n---\n"

    # Act / Assert
    with pytest.raises(AssertionError, match="Drift version"):
        _assert_same_version(reference, mutated)


def test_stale_checker_detects_and_ignores() -> None:
    """Mutation-style: el checker detecta el token obsoleto sin falsos positivos."""
    # Arrange
    stale = "SEG: 0 secrets | validate input | mask logs"
    clean = "SEG: 0 secrets | mask logs | parametriza SQL"

    # Act / Assert
    assert _stale_seg_lines(stale), "No detecto 'SEG: ... validate input'"
    assert _stale_seg_lines(clean) == [], "Falso positivo en SEG valido"


def test_mutation_adr_missing_section_detected() -> None:
    """Mutation-style: un ADR sin 'Consecuencias' es detectado."""
    # Arrange
    incomplete = "## Status\n## Date\n## Contexto\n## Decision\n"

    # Act / Assert
    assert "Consecuencias" in _missing_adr_sections(incomplete)