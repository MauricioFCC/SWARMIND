"""Tests de fitness para la integracion de ADR-0098 en los principios base.

Valida que los 5 codigos del ADR-0098 (CLA, VAL, FST, AAA, ATM) queden
promovidos al bloque N1, registrados en la taxonomia de adherencia e
identicos entre ``base_principles.md`` y ``base_principles.min.md``
(anti-drift). Incluye chequeos adversariales (duplicados, presupuesto de
lineas, atomicidad) y asserts mutation-style que demuestran el poder
discriminante de los checkers.

Contexto: WS-A (principios) y WS-B (agentes) se integran en paralelo; si la
integracion aun no esta completa, los tests de integracion quedan en RED —
es el estado esperado (TDD Spec-First, ``SPE``/``GATE``).

Mutation testing: ``mutmut`` no es viable en Windows nativo (requiere WSL),
por eso se emplean asserts mutation-style como oraculo sustituto.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Rutas y constantes (MAG)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
BASE_PRINCIPLES = ROOT / ".opencode" / "core" / "base_principles.md"
MIN_PRINCIPLES = ROOT / ".opencode" / "core" / "base_principles.min.md"
AGENTS_DIR = ROOT / ".opencode" / "agents"
VALIDATE_SKILLS = ROOT / "scripts" / "validate_skills.py"
BASE_SKILL_TEMPLATE = ROOT / ".opencode" / "core" / "base_skill_template.md"

#: Codigos ADR-0098 -> categoria de la taxonomia de adherencia.
ADR0098_CODES: dict[str, str] = {
    "CLA": "ARC",
    "VAL": "SEC",
    "FST": "GOV",
    "AAA": "QLT",
    "ATM": "PRC",
}

ADR0098_TAG = "ADR-0098"
MIN_VERSION = (3, 5, 0)
N1_MAX_LINES = 60
VALIDATE_SKILLS_TIMEOUT_SECONDS = 120

_CODE_LINE_RE = re.compile(r"^([A-Z][A-Z0-9]{1,4}):")
_TAXONOMY_ROW_RE = re.compile(r"^\|\s*([A-Z]{3})\s*\|([^|]*)\|([^|]*)\|([^|]*)\|")
_VERSION_RE = re.compile(r"^version:\s*([0-9]+(?:\.[0-9]+)*)", re.MULTILINE)

#: Bloque N1 sintetico minimo para probar los checkers (no depende del repo).
_SYNTHETIC_N1 = (
    "RSF: Research First | investigar ANTES\n"
    "CLA: Clean Architecture | dominio puro\n"
    "VAL: Input Validation | valida contra schema\n"
    "FST: Fail-Fast tipado | cause + contexto\n"
    "AAA: Test AAA | Arrange-Act-Assert\n"
    "ATM: Atomic Changes | un commit una preocupacion\n"
)


# ---------------------------------------------------------------------------
# Helpers (checkers puros, reutilizados por los asserts mutation-style)
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
    """Extrae el primer bloque cercado (``` ... ```) de un texto Markdown.

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


def _codes_in_block(block: str) -> list[str]:
    """Devuelve los codigos N1 (prefijo MAYUSCULAS:) de un bloque, en orden.

    Args:
        block: Cuerpo del bloque N1.

    Returns:
        Lista de codigos detectados.
    """
    codes: list[str] = []
    for line in block.splitlines():
        match = _CODE_LINE_RE.match(line.strip())
        if match:
            codes.append(match.group(1))
    return codes


def _assert_n1_contains_codes(block: str, required: dict[str, str]) -> None:
    """Verifica que el bloque N1 contenga todos los codigos requeridos.

    Args:
        block: Cuerpo del bloque N1.
        required: Codigos esperados (claves del diccionario).

    Raises:
        AssertionError: Si falta algun codigo.
    """
    present = set(_codes_in_block(block))
    missing = sorted(set(required) - present)
    assert not missing, f"N1 no contiene los codigos: {missing}"


def _normalize_taxonomy_token(token: str) -> str:
    """Extrae el codigo de una celda de taxonomia (ignora anotaciones).

    Args:
        token: Celda cruda, p.ej. ``CLA (ADR-0098)`` o ``ARQ``.

    Returns:
        Codigo normalizado, p.ej. ``CLA``.
    """
    return re.split(r"[\s(]", token.strip().strip("`"), maxsplit=1)[0]

def _taxonomy_map(text: str) -> dict[str, set[str]]:
    """Mapea categoria -> conjunto de codigos desde la tabla de taxonomia.

    Args:
        text: Contenido de base_principles.md.

    Returns:
        Diccionario categoria -> codigos.
    """
    taxonomy: dict[str, set[str]] = {}
    for line in text.splitlines():
        match = _TAXONOMY_ROW_RE.match(line)
        if match:
            category = match.group(1)
            codes = {_normalize_taxonomy_token(code) for code in match.group(3).split(",") if code.strip()}
            taxonomy.setdefault(category, set()).update(codes)
    return taxonomy


def _assert_taxonomy_mapping(text: str, expected: dict[str, str]) -> None:
    """Verifica que cada codigo este en la categoria esperada de la taxonomia.

    Args:
        text: Contenido de base_principles.md.
        expected: Codigo -> categoria esperada.

    Raises:
        AssertionError: Si una categoria falta o el codigo no esta en ella.
    """
    taxonomy = _taxonomy_map(text)
    for code, category in expected.items():
        assert category in taxonomy, f"Taxonomia sin categoria {category} (esperada para {code})"
        assert code in taxonomy[category], (
            f"Taxonomia: {code} debe pertenecer a {category}, "
            f"encontrado en {[cat for cat, codes in taxonomy.items() if code in codes]}"
        )


def _assert_no_duplicate_codes(block: str) -> None:
    """Verifica que ningun codigo N1 aparezca mas de una vez.

    Args:
        block: Cuerpo del bloque N1.

    Raises:
        AssertionError: Si hay codigos duplicados.
    """
    codes = _codes_in_block(block)
    duplicates = sorted({code for code in codes if codes.count(code) > 1})
    assert not duplicates, f"N1 con codigos duplicados: {duplicates}"


def _assert_n1_within_budget(block: str, max_lines: int) -> None:
    """Verifica que el bloque N1 no exceda el presupuesto de lineas.

    Args:
        block: Cuerpo del bloque N1.
        max_lines: Maximo de lineas no vacias permitido.

    Raises:
        AssertionError: Si excede el presupuesto.
    """
    line_count = len([line for line in block.splitlines() if line.strip()])
    assert line_count <= max_lines, f"N1 anti-bloat: {line_count} lineas > {max_lines}"


def _line_for_code(block: str, code: str) -> str:
    """Devuelve la linea N1 que define un codigo.

    Args:
        block: Cuerpo del bloque N1.
        code: Codigo a buscar.

    Returns:
        Linea que inicia con ``code:``.

    Raises:
        AssertionError: Si el codigo no esta presente.
    """
    for line in block.splitlines():
        if line.strip().startswith(f"{code}:"):
            return line.strip()
    raise AssertionError(f"N1 sin linea para el codigo {code}")


def _assert_lines_atomic(block: str, codes: dict[str, str]) -> None:
    """Verifica que las lineas de los codigos dados sean atomicas.

    Un criterio atomico no usa conjunciones (" and "/" y ") que mezclen dos
    reglas en una (DRFR/NAM).

    Args:
        block: Cuerpo del bloque N1.
        codes: Codigos cuyas lineas se validan.

    Raises:
        AssertionError: Si una linea contiene conjunciones prohibidas.
    """
    for code in codes:
        line = _line_for_code(block, code)
        lowered = line.lower()
        assert " and " not in lowered and " y " not in lowered, (
            f"Linea N1 no atomica para {code!r}: {line}"
        )


def _frontmatter_version(text: str) -> tuple[int, ...]:
    """Extrae y normaliza la version del frontmatter YAML.

    Args:
        text: Contenido Markdown con frontmatter.

    Returns:
        Tupla de 3 enteros (major, minor, patch).

    Raises:
        AssertionError: Si no hay campo ``version``.
    """
    match = _VERSION_RE.search(text)
    assert match is not None, "Frontmatter sin campo 'version'"
    parts = [int(part) for part in match.group(1).split(".")]
    return tuple((parts + [0, 0, 0])[:3])


def _assert_same_codes(reference: str, other: str) -> None:
    """Verifica que dos bloques N1 tengan el mismo conjunto de codigos.

    Args:
        reference: Bloque N1 de referencia.
        other: Bloque N1 a comparar.

    Raises:
        AssertionError: Si los conjuntos de codigos difieren (drift).
    """
    reference_codes = set(_codes_in_block(reference))
    other_codes = set(_codes_in_block(other))
    assert reference_codes == other_codes, (
        f"Drift N1/min: solo en base={sorted(reference_codes - other_codes)}, "
        f"solo en min={sorted(other_codes - reference_codes)}"
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_text() -> str:
    """Contenido de ``base_principles.md`` para los tests de integracion."""
    return _read(BASE_PRINCIPLES)


# ---------------------------------------------------------------------------
# Integracion estructural (GREEN cuando WS-A/WS-B cierren)
# ---------------------------------------------------------------------------


def test_base_principles_n1_has_adr0098_codes(base_text: str) -> None:
    """El bloque N1 contiene las lineas CLA:, VAL:, FST:, AAA: y ATM:."""
    n1_block = _extract_first_fenced_block(base_text)

    _assert_n1_contains_codes(n1_block, ADR0098_CODES)


def test_taxonomy_maps_adr0098_codes(base_text: str) -> None:
    """La taxonomia asigna CLA->ARC, VAL->SEC, FST->GOV, AAA->QLT y ATM->PRC."""
    _assert_taxonomy_mapping(base_text, ADR0098_CODES)


def test_min_n1_matches_base_n1(base_text: str) -> None:
    """El conjunto de codigos N1 de min.md es identico al de base_principles.md."""
    min_text = _read(MIN_PRINCIPLES)
    base_n1 = _extract_first_fenced_block(base_text)
    min_n1 = _extract_first_fenced_block(min_text)

    _assert_same_codes(base_n1, min_n1)


def test_version_bumped(base_text: str) -> None:
    """El frontmatter version es >= 3.5.0 en base_principles.md y min.md."""
    min_text = _read(MIN_PRINCIPLES)
    base_version = _frontmatter_version(base_text)
    min_version = _frontmatter_version(min_text)

    assert base_version >= MIN_VERSION, (
        f"base_principles.md version {base_version} < {MIN_VERSION}"
    )
    assert min_version >= MIN_VERSION, (
        f"base_principles.min.md version {min_version} < {MIN_VERSION}"
    )


def test_all_agents_reference_adr0098() -> None:
    """Cada agente .md (no .agent.min.md) referencia ADR-0098."""
    agent_files = [
        path
        for path in sorted(AGENTS_DIR.glob("*.md"))
        if not path.name.endswith(".agent.min.md")
    ]
    assert agent_files, "No se encontraron agentes en .opencode/agents"

    missing = [path.name for path in agent_files if ADR0098_TAG not in _read(path)]

    assert not missing, f"Agentes sin {ADR0098_TAG}: {missing}"

def test_base_skill_template_mentions_adr0098() -> None:
    """La plantilla base de skills menciona ADR-0098."""
    template_text = _read(BASE_SKILL_TEMPLATE)

    assert ADR0098_TAG in template_text, f"base_skill_template.md sin {ADR0098_TAG}"


def test_validate_skills_strict_passes() -> None:
    """``scripts/validate_skills.py --strict`` termina con exit 0."""
    result = subprocess.run(
        [sys.executable, str(VALIDATE_SKILLS), "--strict", "--quiet"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=VALIDATE_SKILLS_TIMEOUT_SECONDS,
    )

    assert result.returncode == 0, (
        f"validate_skills --strict exit={result.returncode}\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Adversarial: duplicados, anti-bloat, atomicidad
# ---------------------------------------------------------------------------


def test_n1_has_no_duplicate_codes(base_text: str) -> None:
    """N1 no repite ningun codigo (regla duplicada exacta)."""
    n1_block = _extract_first_fenced_block(base_text)

    _assert_no_duplicate_codes(n1_block)


def test_n1_within_line_budget(base_text: str) -> None:
    """N1 no excede el presupuesto anti-bloat de 60 lineas."""
    n1_block = _extract_first_fenced_block(base_text)

    _assert_n1_within_budget(n1_block, N1_MAX_LINES)


def test_adr0098_lines_are_atomic(base_text: str) -> None:
    """Las lineas N1 de los 5 codigos no mezclan dos reglas (sin ' y '/' and ')."""
    n1_block = _extract_first_fenced_block(base_text)

    _assert_lines_atomic(n1_block, ADR0098_CODES)


# ---------------------------------------------------------------------------
# Mutation-style: demuestran que los checkers matan al mutante
# ---------------------------------------------------------------------------


def test_mutation_detects_missing_cla_code() -> None:
    """Mutation-style: un N1 sin CLA es RECHAZADO (mata al mutante que lo elimina)."""
    mutated_n1 = "\n".join(
        line for line in _SYNTHETIC_N1.splitlines() if not line.startswith("CLA:")
    )

    with pytest.raises(AssertionError, match="CLA"):
        _assert_n1_contains_codes(mutated_n1, ADR0098_CODES)


def test_mutation_detects_swapped_taxonomy_mapping() -> None:
    """Mutation-style: CLA asignado a SEC (en vez de ARC) es RECHAZADO."""
    mutated_taxonomy = (
        "| Cat | Nombre | Codigos | Modo |\n"
        "|-----|--------|---------|------|\n"
        "| ARC | Arquitectura | ARQ, SOL | CHECK |\n"
        "| SEC | Seguridad | SEG, CLA | CHECK |\n"
        "| GOV | Gobernanza | ERR, FST | CHECK |\n"
        "| QLT | Calidad | TST, AAA | CHECK |\n"
        "| PRC | Proceso | RSF, ATM | CHECK |\n"
    )

    with pytest.raises(AssertionError, match="CLA"):
        _assert_taxonomy_mapping(mutated_taxonomy, ADR0098_CODES)


def test_mutation_checker_rejects_absent_code() -> None:
    """Mutation-style: exigir un codigo ausente falla (el checker discrimina)."""
    with pytest.raises(AssertionError, match="ZZZ"):
        _assert_n1_contains_codes(_SYNTHETIC_N1, {"ZZZ": "ARC"})


def test_mutation_min_extra_code_is_detected() -> None:
    """Mutation-style: un min.md con un codigo extra rompe el anti-drift."""
    mutated_min = _SYNTHETIC_N1 + "ZZZ: regla fantasma | no existe\n"

    with pytest.raises(AssertionError, match="ZZZ"):
        _assert_same_codes(_SYNTHETIC_N1, mutated_min)