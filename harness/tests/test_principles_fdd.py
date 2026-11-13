"""Tests de fitness del merge FDD/DDD/SDD en los principios v4.0.0.

Valida los criterios de aceptación de ``docs/specs/principles-v4-fdd-merge.md``:

1. El N1 incorpora los seis códigos FDD/DDD con sus invariantes.
2. El N1 respeta el presupuesto (47 códigos, <=60 líneas, sin duplicados).
3. La taxonomía es una biyección exacta sobre el N1 (sin ausentes ni fantasmas).
4. La categoría ``FDD`` y ``GOV`` contienen los códigos esperados.
5. El N2 incluye la matriz de selección «-DD».
6. Los códigos degradados viven en N2 y sus alias resuelven.
7. Existen los artefactos ``docs/fdd/`` con los cuatro hitos.
8. El guard de duplicados es O(n) y equivale al oráculo O(n²).

Mutation-style: se comparan conjuntos exactos (no solo pertenencia), de modo
que borrar un código, añadir un fantasma o duplicar una fila rompe el test.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from harness.context.principles_guard import (
    DEPRECATED_N1_ALIASES,
    duplicate_codes,
    duplicate_codes_naive,
    n1_codes,
    taxonomy_drift,
    taxonomy_map,
)

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / ".opencode" / "core" / "base_principles.md"
MIN = ROOT / ".opencode" / "core" / "base_principles.min.md"
FULL = ROOT / ".opencode" / "core" / "base_principles_full.md"
FDD_DIR = ROOT / "docs" / "fdd"

N1_MAX_LINES = 60
EXPECTED_N1_CODES = 47
EXPECTED_VERSION = (4, 0, 0)

FDD_CODES: dict[str, tuple[str, ...]] = {
    "DOM": ("mapa de dominio", "lenguaje ubicuo"),
    "FIC": ("ficha por feature", "corte vertical"),
    "HIT": ("hitos", "persona"),
    "FRC": ("friccion proporcional", "irreversible"),
    "OWN": ("un solo coordinador", "dueno"),
    "DEC": ("decisiones cerradas", "invariantes"),
}

DEMOTED_CODES = ("WFP", "MCL", "MKS", "RPA")
FDD_CATEGORY_CODES = {"DOM", "FIC", "FRC", "OWN"}
GOV_FDD_CODES = {"HIT", "DEC"}
DD_TOKENS = ("FDD", "DDD", "SDD", "CDD", "TDD", "BDD", "ATDD", "RDD")

_VERSION_RE = re.compile(r"^version:\s*([0-9]+(?:\.[0-9]+)*)", re.MULTILINE)


class _HashCounter:
    """Objeto hashable que cuenta cuántas veces se calcula su hash."""

    __slots__ = ("value",)
    hash_calls: ClassVar[int] = 0

    def __init__(self, value: str) -> None:
        """Guarda el valor envuelto.

        Args:
            value: Texto a envolver.
        """
        self.value = value

    def __hash__(self) -> int:
        """Incrementa el contador y devuelve el hash del valor."""
        type(self).hash_calls += 1
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        """Compara por valor envuelto.

        Args:
            other: Otro objeto.

        Returns:
            ``True`` si envuelve el mismo texto.
        """
        return isinstance(other, _HashCounter) and self.value == other.value


class _EqCounter:
    """Objeto que cuenta cuántas veces se compara por igualdad."""

    __slots__ = ("value",)
    eq_calls: ClassVar[int] = 0

    def __init__(self, value: str) -> None:
        """Guarda el valor envuelto.

        Args:
            value: Texto a envolver.
        """
        self.value = value

    def __hash__(self) -> int:
        """Devuelve un hash estable para el valor envuelto."""
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        """Incrementa el contador y compara por valor envuelto.

        Args:
            other: Otro objeto.

        Returns:
            ``True`` si envuelve el mismo texto.
        """
        type(self).eq_calls += 1
        return isinstance(other, _EqCounter) and self.value == other.value


def _text(path: Path) -> str:
    """Lee un archivo de principios en UTF-8.

    Args:
        path: Ruta del archivo.

    Returns:
        Contenido del archivo.
    """
    return path.read_text(encoding="utf-8")


def _n1_block(text: str) -> str:
    """Devuelve el bloque N1 (primer bloque cercado).

    Args:
        text: Contenido Markdown.

    Returns:
        Cuerpo del bloque N1.
    """
    match = re.search(r"```md\n(.*?)```", text, re.DOTALL)
    assert match is not None, "Sin bloque N1 cercado"
    return match.group(1)


def _n2_region(text: str) -> str:
    """Devuelve la sección N2 (entre los encabezados de nivel 2 y 3).

    Args:
        text: Contenido de ``base_principles.md``.

    Returns:
        Texto de la sección N2.
    """
    start = text.index("## NIVEL 2")
    end = text.index("## NIVEL 3")
    return text[start:end]


def _line_for(block: str, code: str) -> str:
    """Devuelve la línea N1 de un código.

    Args:
        block: Cuerpo del bloque N1.
        code: Código buscado.

    Returns:
        Línea normalizada.

    Raises:
        AssertionError: Si el código no está en el bloque.
    """
    for line in block.splitlines():
        if line.strip().startswith(f"{code}:"):
            return line.strip().lower()
    raise AssertionError(f"N1 sin linea para {code}")


@pytest.mark.parametrize(("code", "keywords"), FDD_CODES.items())
def test_n1_has_fdd_codes(code: str, keywords: tuple[str, ...]) -> None:
    """AC-01: cada código FDD/DDD existe en base y min con sus invariantes."""
    for path in (BASE, MIN):
        line = _line_for(_n1_block(_text(path)), code)
        for keyword in keywords:
            assert keyword in line, f"{path.name}: {code} sin {keyword!r}"


def test_n1_budget_and_count() -> None:
    """AC-02: 47 códigos exactos, sin duplicados y <=60 líneas."""
    for path in (BASE, MIN):
        text = _text(path)
        codes = n1_codes(text)
        block = _n1_block(text)
        assert len(codes) == EXPECTED_N1_CODES, f"{path.name}: {len(codes)} codigos"
        assert len(set(codes)) == EXPECTED_N1_CODES, f"{path.name}: codigos duplicados"
        assert duplicate_codes(codes) == []
        assert len([line for line in block.splitlines() if line.strip()]) <= N1_MAX_LINES


def test_taxonomy_is_exact_bijection() -> None:
    """AC-04: taxonomía == N1 (sin ausentes ni fantasmas)."""
    text = _text(BASE)
    missing, ghosts = taxonomy_drift(n1_codes(text), taxonomy_map(text))
    assert missing == [], f"N1 sin categoria: {missing}"
    assert ghosts == [], f"Taxonomia con fantasmas: {ghosts}"
    for ghost in ("DOR", "OPS", "QLT"):
        assert ghost not in n1_codes(text), f"{ghost} no debe volver al N1"


def test_fdd_and_gov_taxonomy() -> None:
    """AC-05: FDD = {DOM, FIC, FRC, OWN} y GOV incluye HIT/DEC."""
    taxonomy = taxonomy_map(_text(BASE))
    assert taxonomy["FDD"] == FDD_CATEGORY_CODES
    assert GOV_FDD_CODES <= taxonomy["GOV"]
    assert {"CLA"} <= taxonomy["ARC"]
    assert {"VAL"} <= taxonomy["SEC"]
    assert {"FST"} <= taxonomy["GOV"]
    assert {"AAA"} <= taxonomy["QLT"]
    assert {"ATM"} <= taxonomy["PRC"]


def test_n2_has_dd_selection_matrix() -> None:
    """AC-06: el N2 documenta la matriz de selección «-DD»."""
    n2 = _n2_region(_text(BASE))
    assert "matriz" in n2.lower(), "N2 sin matriz de seleccion"
    for token in DD_TOKENS:
        assert token in n2, f"Matriz N2 sin {token}"


def test_demoted_codes_have_home() -> None:
    """AC-07: los GUIDE degradados viven en N2 y sus alias resuelven."""
    text = _text(BASE)
    codes = set(n1_codes(text))
    n2 = _n2_region(text)
    for code in DEMOTED_CODES:
        assert code not in codes, f"{code} sigue en N1"
        assert f"__{code}__" in n2, f"{code} sin fila en N2"
        assert DEPRECATED_N1_ALIASES[code] in text, f"Alias de {code} sin ancla"


def test_fdd_artifacts_exist() -> None:
    """AC-08: existen los artefactos FDD y la ficha declara los 4 hitos."""
    for name in ("README.md", "dominio.md", "ficha-template.md"):
        assert (FDD_DIR / name).is_file(), f"Falta docs/fdd/{name}"
    ficha = (FDD_DIR / "ficha-template.md").read_text(encoding="utf-8").lower()
    for milestone in ("diseñado", "implementado", "verificado", "integrado"):
        assert milestone in ficha, f"Ficha sin hito {milestone}"
    dominio = (FDD_DIR / "dominio.md").read_text(encoding="utf-8").lower()
    assert "entidad" in dominio and "lenguaje ubicuo" in dominio


def test_versions_are_v4() -> None:
    """AC-11: las tres copias declaran la versión 4.0.0."""
    for path in (BASE, MIN, FULL):
        match = _VERSION_RE.search(_text(path))
        assert match is not None, f"{path.name} sin version"
        version = tuple(int(part) for part in match.group(1).split("."))
        assert version == EXPECTED_VERSION, f"{path.name}: {version}"


@given(st.lists(st.sampled_from(sorted(FDD_CODES) + list(DEMOTED_CODES)), max_size=40))
def test_duplicates_equivalent_to_oracle(codes: list[str]) -> None:
    """AC-09: el guard O(n) equivale al oráculo O(n²)."""
    assert duplicate_codes(codes) == duplicate_codes_naive(codes)


def _hash_calls_for(n: int) -> int:
    """Cuenta hashes del guard para ``n`` códigos únicos.

    Args:
        n: Cantidad de códigos.

    Returns:
        Número de llamadas a ``__hash__``.
    """
    values = [cast(str, _HashCounter(f"C{index:04d}")) for index in range(n)]
    _HashCounter.hash_calls = 0
    assert duplicate_codes(values) == []
    return _HashCounter.hash_calls


def _eq_calls_for(n: int) -> int:
    """Cuenta comparaciones del oráculo para ``n`` códigos únicos.

    Args:
        n: Cantidad de códigos.

    Returns:
        Número de llamadas a ``__eq__``.
    """
    values = [cast(str, _EqCounter(f"C{index:04d}")) for index in range(n)]
    _EqCounter.eq_calls = 0
    assert duplicate_codes_naive(values) == []
    return _EqCounter.eq_calls


def test_duplicates_scaling() -> None:
    """AC-10: el guard es lineal; el oráculo crece cuadráticamente."""
    small, large = _hash_calls_for(50), _hash_calls_for(100)
    assert small <= 3 * 50, f"Guard con demasiados hashes: {small}"
    assert large <= 2.5 * small, f"Guard no lineal: {small} -> {large}"

    eq_small, eq_large = _eq_calls_for(50), _eq_calls_for(100)
    assert eq_large >= 3 * eq_small, f"Oraculo no cuadratico: {eq_small} -> {eq_large}"
