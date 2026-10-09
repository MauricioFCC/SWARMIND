"""keyword_match.py — matching de keywords por frontera de palabra (anti falsos positivos).

WHAT: utilidades de matching con normalizacion (minusculas, acentos, guiones) y
**limite de palabra**, para que `"api"` NO matchee `"capital"`, `"doc"` NO
matchee `"docker"`, `"go"` NO matchee `"good"`, `"pos"` NO matchee `"position"`.
WHY: el matching por substring (`keyword in texto`) es la causa raiz de falsos
positivos en deteccion de dominio/agente/skill (tomar/descartar mal) y de
inyeccion de triggers (prompt injection a la seleccion). Un matcher unico y
determinista elimina la duplicacion de heuristicas (DRY) y hace la seleccion
verificable.
WHERE: `skill_bundler.detect_domain/select_skills`, `agent_selector._score_agents`,
`delegation_engine._match_intent`, `difficulty_router` (todos los que hoy usan
`keyword in texto`).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

#: Caracteres que se tratan como separador de palabra (no parte del token).
_SEPARATOR_RE = re.compile(r"[-_]+")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Normaliza texto para matching: minusculas, sin acentos, guiones a espacio.

    Aplica NFKD y elimina marcas diacriticas (`diseña` -> `disena`), convierte
    `-`/`_` en espacio y colapsa espacios. Asi `"micro-servicio"` matchea
    `"micro servicio"` y `"disena"` matchea `"diseña"`.

    Args:
        text: Texto de entrada (tarea, keyword, etc.).

    Returns:
        Texto normalizado (str; "" si la entrada es vacia).
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = without_marks.lower()
    spaced = _SEPARATOR_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", spaced).strip()


def contains_word(text: str, keyword: str) -> bool:
    """True si `keyword` aparece como palabra completa en `text` (normalizados).

    Usa frontera de palabra (`\\b`): `"api"` no matchea `"capital"`, `"doc"` no
    matchea `"docker"`. Las keywords multi-palabra (`"position sizing"`) se
    matchean como frase con frontera en los extremos.

    Args:
        text: Texto donde buscar.
        keyword: Keyword (simple o multi-palabra) a matchear.

    Returns:
        True si hay match por palabra; False si `keyword` es vacio.
    """
    norm_kw = normalize(keyword)
    if not norm_kw:
        return False
    norm_text = normalize(text)
    if not norm_text:
        return False
    pattern = rf"(?<!\w){re.escape(norm_kw)}(?!\w)"
    return re.search(pattern, norm_text) is not None


def match_keywords(text: str, keywords: Iterable[str]) -> tuple[str, ...]:
    """Devuelve las keywords (originales) que matchean como palabra en `text`.

    Args:
        text: Texto donde buscar.
        keywords: Iterable de keywords.

    Returns:
        Tupla de keywords que matchean, en el orden de `keywords`.
    """
    return tuple(kw for kw in keywords if contains_word(text, kw))


def score_keywords(text: str, keywords: Iterable[str]) -> int:
    """Cuenta cuantas keywords matchean como palabra en `text`.

    Args:
        text: Texto donde buscar.
        keywords: Iterable de keywords.

    Returns:
        Numero de keywords que matchean (>= 0).
    """
    return len(match_keywords(text, keywords))
