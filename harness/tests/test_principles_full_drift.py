"""Tests de fitness anti-drift para ``base_principles_full.md`` (DRY).

``base_principles_full.md`` debe contener SOLO Nivel 3 (checklists
extendidos, mapa de roles y abreviaciones). Los niveles N1 (esencial) y N2
(estandar) viven UNA sola vez en ``base_principles.md`` (SSOT). Estos tests
detectan el drift clasico: que ``_full.md`` reincorpore bloques N1/N2
desactualizados (p.ej. ``SEG: 0 secrets | validate input | mask logs``, o la
fila de tabla N2 ``| __RSF__ | ... |``).

Mutation-style: se incluyen asserts que prueban que los checkers matan al
mutante (bloque N1 obsoleto, fila de tabla N2, SSOT ausente).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Rutas y constantes (MAG)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
BASE_PRINCIPLES = ROOT / ".opencode" / "core" / "base_principles.md"
FULL_PRINCIPLES = ROOT / ".opencode" / "core" / "base_principles_full.md"

FULL_VERSION = (3, 5, 0)
SSOT_FILENAME = "base_principles.md"
N3_ADR_TAG = "### ADR-0098"

#: Fragmento N1 obsoleto que introducia el drift en _full.md (v2.7.0).
STALE_N1_FRAGMENT = "SEG: 0 secrets | validate input"
#: Marcadores de filas de la tabla N2 (no deben reaparecer en _full.md).
N2_TABLE_MARKERS = ("__RSF__", "__TST__")

_CODE_LINE_RE = re.compile(r"^([A-Z][A-Z0-9]{1,4}):")
_VERSION_RE = re.compile(r"^version:\s*([0-9]+(?:\.[0-9]+)*)", re.MULTILINE)


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


def _frontmatter_version(text: str) -> tuple[int, int, int]:
    """Extrae y normaliza la version del frontmatter YAML.

    Args:
        text: Contenido Markdown con frontmatter.

    Returns:
        Tupla (major, minor, patch).

    Raises:
        AssertionError: Si no hay campo ``version``.
    """
    match = _VERSION_RE.search(text)
    assert match is not None, "Frontmatter sin campo 'version'"
    parts = [int(part) for part in match.group(1).split(".")]
    padded = (parts + [0, 0, 0])[:3]
    return padded[0], padded[1], padded[2]


def _extract_first_fenced_block(text: str) -> str:
    """Extrae el primer bloque cercado (``` ... ```) de un Markdown.

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


def _fenced_blocks(text: str) -> list[str]:
    """Devuelve el cuerpo de todos los bloques cercados de un Markdown.

    Args:
        text: Contenido Markdown.

    Returns:
        Lista con el cuerpo de cada bloque cercado (sin las vallas).
    """
    blocks: list[str] = []
    current: list[str] = []
    is_inside = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            if is_inside:
                blocks.append("\n".join(current))
                current = []
            is_inside = not is_inside
            continue
        if is_inside:
            current.append(line)
    return blocks


def _code_lines(block: str) -> dict[str, str]:
    """Mapea codigo N1 -> linea para las lineas ``CODE: ...`` de un bloque.

    Args:
        block: Cuerpo de un bloque.

    Returns:
        Diccionario codigo -> linea (stripped).
    """
    mapping: dict[str, str] = {}
    for line in block.splitlines():
        stripped = line.strip()
        match = _CODE_LINE_RE.match(stripped)
        if match:
            mapping[match.group(1)] = stripped
    return mapping


def _looks_like_n1_block(block: str) -> bool:
    """Indica si TODAS las lineas no vacias del bloque son lineas N1 ``CODE:``.

    Args:
        block: Cuerpo de un bloque cercado.

    Returns:
        ``True`` si el bloque parece el bloque N1 (todas sus lineas son N1).
    """
    non_empty = [line for line in block.splitlines() if line.strip()]
    if not non_empty:
        return False
    return len(_code_lines(block)) == len(non_empty)


def _n1_blocks(text: str) -> list[str]:
    """Bloques cercados del texto que parecen un bloque N1.

    Args:
        text: Contenido Markdown.

    Returns:
        Lista de bloques que parecen N1.
    """
    return [block for block in _fenced_blocks(text) if _looks_like_n1_block(block)]


def _find_n1_drift(base_block: str, candidate_text: str) -> dict[str, tuple[str | None, str]]:
    """Detecta lineas N1 del candidato que difieren de la SSOT.

    Args:
        base_block: Bloque N1 de la SSOT (``base_principles.md``).
        candidate_text: Texto candidato (``_full.md``) a auditar.

    Returns:
        Diccionario codigo -> (linea_ssot, linea_candidato) con cada drift.
    """
    base_lines = _code_lines(base_block)
    drift: dict[str, tuple[str | None, str]] = {}
    for block in _n1_blocks(candidate_text):
        for code, line in _code_lines(block).items():
            if base_lines.get(code) != line:
                drift[code] = (base_lines.get(code), line)
    return drift


def _contains_n2_table_row(text: str) -> bool:
    """Indica si el texto contiene una fila de la tabla N2 de la SSOT.

    Args:
        text: Contenido Markdown.

    Returns:
        ``True`` si aparece algun marcador de fila ``__CODE__`` de N2.
    """
    return any(marker in text for marker in N2_TABLE_MARKERS)


def _mentions_ssot(text: str) -> bool:
    """Indica si el texto referencia ``base_principles.md`` como SSOT de N1/N2.

    Args:
        text: Contenido Markdown.

    Returns:
        ``True`` si menciona el archivo SSOT y explicita N1/N2.
    """
    lowered = text.lower()
    return (
        SSOT_FILENAME in text
        and "ssot" in lowered
        and "n1" in lowered
        and "n2" in lowered
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_text() -> str:
    """Contenido de ``base_principles.md`` (SSOT N1/N2)."""
    return _read(BASE_PRINCIPLES)


# ---------------------------------------------------------------------------
# Integracion: _full.md = SOLO N3, apuntando a la SSOT
# ---------------------------------------------------------------------------


def test_full_version_matches_base() -> None:
    """La version de ``_full.md`` es identica a la de ``base_principles.md``."""
    base_version = _frontmatter_version(_read(BASE_PRINCIPLES))
    full_version = _frontmatter_version(_read(FULL_PRINCIPLES))

    assert full_version == base_version, (
        f"Drift de version: full={full_version} base={base_version}"
    )
    assert full_version >= FULL_VERSION, (
        f"_full.md version {full_version} < {FULL_VERSION}"
    )


def test_full_has_no_stale_n1_block(base_text: str) -> None:
    """``_full.md`` no duplica N1 obsoleto; su N1 (si aparece) iguala a la SSOT."""
    full_text = _read(FULL_PRINCIPLES)

    assert STALE_N1_FRAGMENT not in full_text, (
        f"drift: _full.md contiene la linea N1 obsoleta {STALE_N1_FRAGMENT!r}"
    )

    base_block = _extract_first_fenced_block(base_text)
    drift = _find_n1_drift(base_block, full_text)

    assert not drift, f"_full.md con N1 drifted vs SSOT: {drift}"


def test_full_points_to_ssot() -> None:
    """``_full.md`` declara ``base_principles.md`` como SSOT de N1/N2."""
    full_text = _read(FULL_PRINCIPLES)

    assert _mentions_ssot(full_text), (
        "_full.md no apunta a base_principles.md como SSOT de N1/N2"
    )


def test_full_keeps_n3_adr0098() -> None:
    """``_full.md`` conserva la seccion N3 del ADR-0098."""
    full_text = _read(FULL_PRINCIPLES)

    assert N3_ADR_TAG in full_text, f"_full.md sin seccion {N3_ADR_TAG!r}"


def test_full_has_no_n2_table_duplicate() -> None:
    """``_full.md`` no reincorpora la tabla N2 (filas ``__CODE__`` de la SSOT)."""
    full_text = _read(FULL_PRINCIPLES)
    duplicates = [marker for marker in N2_TABLE_MARKERS if marker in full_text]

    assert not duplicates, f"_full.md duplica la tabla N2: {duplicates}"


# ---------------------------------------------------------------------------
# Mutation-style: demuestran que los checkers matan al mutante
# ---------------------------------------------------------------------------

_BASE_N1_SYNTHETIC = (
    "RSF: Research First | investigar ANTES\n"
    "SEG: 0 secrets | mask logs | parametriza SQL\n"
    "TST: core >=80% | pre-commit gates\n"
)


def test_mutation_detects_stale_seg_line() -> None:
    """Mutation-style: un bloque N1 con ``SEG`` obsoleto es RECHAZADO."""
    candidate = (
        "```md\n"
        "RSF: Research First | investigar ANTES\n"
        "SEG: 0 secrets | validate input | mask logs | parametriza SQL\n"
        "```\n"
    )

    drift = _find_n1_drift(_BASE_N1_SYNTHETIC, candidate)

    assert "SEG" in drift, "el checker no detecto el drift de SEG"
    assert "RSF" not in drift, "el checker marcó una linea sincronizada como drift"


def test_mutation_detects_n2_table_row() -> None:
    """Mutation-style: una fila de tabla N2 (``__RSF__``) es detectada."""
    candidate = "| Cat | Reglas |\n|-----|--------|\n| __RSF__ | Research First |\n"

    assert _contains_n2_table_row(candidate), "el checker no detecto la tabla N2"


def test_mutation_detects_missing_ssot() -> None:
    """Mutation-style: un ``_full.md`` sin SSOT explicita es detectado."""
    candidate = "# full\n\n## NIVEL 3\n\n### ADR-0098\n"

    assert not _mentions_ssot(candidate), "el checker no detecto la SSOT ausente"


def test_mutation_synced_n1_is_not_flagged() -> None:
    """Mutation-style: un N1 identico a la SSOT NO se marca como drift."""
    candidate = "```md\nRSF: Research First | investigar ANTES\nSEG: 0 secrets | mask logs | parametriza SQL\n```\n"

    drift = _find_n1_drift(_BASE_N1_SYNTHETIC, candidate)

    assert not drift, f"falso positivo: {drift}"
