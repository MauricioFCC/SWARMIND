"""Tests de estructura (MADR/Nygard) para los ADR del repositorio.

Valida que el ADR-0098 sea un ADR formal: titulo ``# ADR-0098``, etiquetas
Status/Date, secciones Contexto/Decision/Consecuencias, Status valido y mapeo
explicito de los codigos ``CLA``/``VAL``/``FST``/``AAA``/``ATM``. Ademas
comprueba de forma leniente el titulo de TODOS los ADR de ``docs/adr``: los
heredados sin prefijo ``# ADR-`` se marcan ``xfail`` (no se falla el repo por
ADRs ajenos).

Sin red: solo lectura de archivos (determinista).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Rutas y constantes (MAG)
# ---------------------------------------------------------------------------

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_0098_PATH = ADR_DIR / "adr-0098-Convenciones-codigo-principios-doce.md"

ADR0098_TITLE = "# ADR-0098"
ADR0098_CODES = ("CLA", "VAL", "FST", "AAA", "ATM")
REQUIRED_LABELS = ("Status:", "Date:")
REQUIRED_SECTIONS = ("## Contexto", "## Decision", "## Consecuencias")
VALID_STATUSES = frozenset(
    {"Proposed", "Accepted", "Deprecated", "Superseded", "Rejected"}
)

_STATUS_RE = re.compile(r"\*\*Status:\*\*\s*([A-Za-z]+)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    """Lee un archivo de texto en UTF-8.

    Args:
        path: Ruta del archivo a leer.

    Returns:
        Contenido del archivo.

    Raises:
        AssertionError: Si el archivo no existe.
    """
    assert path.is_file(), f"Archivo no encontrado: {path}"
    return path.read_text(encoding="utf-8")


def _first_line(text: str) -> str:
    """Devuelve la primera linea no vacia de un texto.

    Args:
        text: Contenido de un archivo Markdown.

    Returns:
        Primera linea con contenido, o cadena vacia si no la hay.
    """
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adr_text() -> str:
    """Contenido del ADR-0098 para los tests de estructura."""
    return _read(ADR_0098_PATH)


# ---------------------------------------------------------------------------
# Estructura del ADR-0098
# ---------------------------------------------------------------------------


def test_adr0098_has_required_sections(adr_text: str) -> None:
    """El ADR-0098 tiene titulo `# ADR-0098` y etiquetas/secciones obligatorias."""
    # Arrange
    required_tokens = (ADR0098_TITLE, *REQUIRED_LABELS, *REQUIRED_SECTIONS)

    # Act
    missing = [token for token in required_tokens if token not in adr_text]

    # Assert
    assert adr_text.startswith(ADR0098_TITLE), (
        f"El ADR debe iniciar con el titulo '{ADR0098_TITLE}'"
    )
    assert not missing, f"Faltan etiquetas/secciones obligatorias: {missing}"


def test_adr0098_status_is_valid(adr_text: str) -> None:
    """El Status del ADR-0098 pertenece al conjunto MADR permitido."""
    # Arrange
    match = _STATUS_RE.search(adr_text)

    # Act
    assert match is not None, "No se encontro la etiqueta '**Status:**'"
    status = match.group(1)

    # Assert
    assert status in VALID_STATUSES, (
        f"Status invalido: {status!r}; esperado uno de {sorted(VALID_STATUSES)}"
    )


def test_adr0098_maps_codes(adr_text: str) -> None:
    """El ADR-0098 menciona los cinco codigos CLA, VAL, FST, AAA y ATM."""
    # Arrange
    expected_codes = set(ADR0098_CODES)

    # Act
    present_codes = {code for code in ADR0098_CODES if code in adr_text}

    # Assert
    assert present_codes == expected_codes, (
        f"Codigos ausentes en el ADR-0098: {sorted(expected_codes - present_codes)}"
    )


# ---------------------------------------------------------------------------
# Titulo de todos los ADR (leniente)
# ---------------------------------------------------------------------------


def test_all_adr_files_have_title() -> None:
    """Cada `docs/adr/*.md` inicia con `# ADR-`; los heredados se marcan xfail.

    No se falla el repo por ADRs ajenos con otro prefijo (p. ej. `# ADR 0089`);
    se documentan como xfail para visibilizar la deuda de estilo sin bloquear.
    """
    # Arrange
    adr_files = sorted(ADR_DIR.glob("*.md"))
    assert adr_files, f"No se encontraron ADRs en {ADR_DIR}"

    # Act
    offenders = [
        path.name
        for path in adr_files
        if not _first_line(_read(path)).startswith("# ADR-")
    ]

    # Assert
    if offenders:
        pytest.xfail(f"ADRs heredados sin prefijo '# ADR-': {offenders}")
    assert not offenders
