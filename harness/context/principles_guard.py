"""Guard de integridad de los principios universales (N1, taxonomía y alias).

WHAT: utilidades puras para extraer códigos N1 de un Markdown, detectar
duplicados en O(n), mapear la taxonomía de adherencia y calcular su deriva
(códigos ausentes y fantasmas), además del mapa de alias de los códigos que
dejaron de ser N1 en v4.0.0.

WHY: los chequeos vivían duplicados en tres suites de tests y la detección de
duplicados era O(n²) (``codes.count(code)`` por código). Una sola
implementación O(n) evita drift entre chequeos y mantiene el gate barato
(research ``frontier-2026-11-12-fdd-principles.md``, spec
``principles-v4-fdd-merge.md``).

WHERE: consumido por ``harness/tests/test_principles_fdd.py``,
``harness/tests/test_principles_adr0098.py`` y futuros validadores CLI.

Invariantes: sin estado global mutable; sin red; sin subprocess; cada función
es determinista y devuelve colecciones ordenadas cuando el orden importa.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType

#: Línea N1: código de 2-5 caracteres (``GATE``, ``FAIL``) seguido de dos puntos.
N1_CODE_RE = re.compile(r"^([A-Z][A-Z0-9]{1,4}):")

#: Fila de la tabla de taxonomía: ``| CAT | Nombre | códigos | modo |``.
TAXONOMY_ROW_RE = re.compile(r"^\|\s*([A-Z]{3})\s*\|([^|]*)\|([^|]*)\|([^|]*)\|")

#: Alias de códigos que salieron de N1 en v4.0.0 -> ancla textual en N2.
#: No se eliminan: siguen siendo códigos citables y su ancla debe existir.
DEPRECATED_N1_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "WFP": "Workflow Patterns",
        "MCL": "MetaClaw",
        "MKS": "Memento-Skills",
        "RPA": "Re-Pin After compaction",
        "DOR": "DORA como SLO",
        "QLT": "DEPRECATED v2.4.0",
    }
)


def extract_first_fenced_block(text: str) -> str:
    """Extrae el primer bloque cercado por ``` del Markdown.

    Args:
        text: Contenido Markdown de una copia de principios.

    Returns:
        Cuerpo del bloque sin las vallas.

    Raises:
        AssertionError: Si no hay bloque cercado o falta el cierre.
    """
    start = text.find("```")
    assert start != -1, "No se encontro bloque cercado (```)"
    first_newline = text.find("\n", start)
    end = text.find("```", first_newline)
    assert end != -1, "Bloque cercado sin cierre (```)"
    return text[first_newline + 1 : end]


def n1_codes(text: str) -> list[str]:
    """Devuelve los códigos N1 del primer bloque cercado, en orden.

    Args:
        text: Contenido Markdown de una copia de principios.

    Returns:
        Lista de códigos N1 detectados.
    """
    block = extract_first_fenced_block(text)
    return [
        match.group(1)
        for line in block.splitlines()
        if (match := N1_CODE_RE.match(line.strip()))
    ]


def duplicate_codes(codes: Iterable[str]) -> list[str]:
    """Detecta códigos repetidos en O(n) esperado.

    Args:
        codes: Secuencia de códigos.

    Returns:
        Códigos repetidos, ordenados alfabéticamente.
    """
    counts = Counter(codes)
    return sorted(code for code, count in counts.items() if count > 1)


def duplicate_codes_naive(codes: Sequence[str]) -> list[str]:
    """Oráculo O(n²) usado para probar equivalencia del guard lineal.

    Args:
        codes: Secuencia de códigos.

    Returns:
        Códigos repetidos, ordenados alfabéticamente.
    """
    repeated = {code for code in codes if codes.count(code) > 1}
    return sorted(repeated)


def taxonomy_map(text: str) -> dict[str, set[str]]:
    """Mapea categoría -> códigos desde la tabla de taxonomía.

    Args:
        text: Contenido Markdown de ``base_principles.md``.

    Returns:
        Diccionario categoría -> conjunto de códigos normalizados.
    """
    taxonomy: dict[str, set[str]] = {}
    for line in text.splitlines():
        match = TAXONOMY_ROW_RE.match(line)
        if not match:
            continue
        category = match.group(1)
        codes = {
            re.split(r"[\s(]", token.strip().strip("`"), maxsplit=1)[0]
            for token in match.group(3).split(",")
            if token.strip()
        }
        taxonomy.setdefault(category, set()).update(codes)
    return taxonomy


def taxonomy_drift(
    codes: Iterable[str], taxonomy: Mapping[str, set[str]]
) -> tuple[list[str], list[str]]:
    """Calcula la deriva entre N1 y taxonomía en O(n+m).

    Args:
        codes: Códigos N1.
        taxonomy: Mapa categoría -> códigos.

    Returns:
        Tupla ``(ausentes, fantasmas)``: códigos N1 sin categoría y códigos de
        la taxonomía que no existen en N1.
    """
    n1 = set(codes)
    mapped = {code for codes_in_category in taxonomy.values() for code in codes_in_category}
    return sorted(n1 - mapped), sorted(mapped - n1)
