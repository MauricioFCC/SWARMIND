"""hidden_body.py — Puntaje por cuerpo de skill (hidden-body asymmetry).

WHAT: puntua el CUERPO real de un skill/agente (``SKILL.md``/``SKILL.min.md``)
por co-ocurrencia de las palabras de la tarea, y lo combina 50/50 con la
similitud de metadata. WHY: la descripcion (metadata) es una senal asimetrica;
el cuerpo revela la relevancia real y reduce el falso positivo del routing
(frontera: SkillRouter, arXiv:2603.22455). WHERE: ``AgentDispatcher.
find_skill_for_task`` y ``SkillBundler.select_skills`` (ADR-0103, FR-C2).

Modulo compartido (DRY): un unico ``_body_keyword_score`` para ambos
consumidores, en vez de duplicar la heuristica.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from pathlib import Path

from harness.orchestrator.keyword_match import normalize

logger = logging.getLogger(__name__)

#: Peso de la similitud de metadata en la combinacion (0.5/0.5).
METADATA_WEIGHT = 0.5
#: Peso del puntaje de cuerpo en la combinacion (0.5/0.5).
BODY_WEIGHT = 0.5

#: Extractor de tokens (secuencias de caracteres de palabra, Unicode).
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> set[str]:
    """Tokeniza texto en palabras normalizadas (minusculas y sin acentos).

    Args:
        text: Texto de entrada (tarea o cuerpo de skill).

    Returns:
        Conjunto de tokens normalizados; ``set()`` si el texto es vacio.
    """
    norm = normalize(text or "")
    if not norm:
        return set()
    return set(_TOKEN_RE.findall(norm))


def _body_keyword_score(body: str, task_words: Iterable[str]) -> float:
    """Fraccion de palabras de la tarea presentes en el cuerpo del skill.

    Args:
        body: Contenido crudo del ``SKILL.md``/``.min.md`` (puede ser vacio).
        task_words: Palabras de la tarea (idealmente ya normalizadas con
            :func:`tokenize`).

    Returns:
        ``matches / len(task_words)`` en ``[0.0, 1.0]``; ``0.0`` si no hay
        palabras de tarea o el cuerpo no aporta tokens.
    """
    words = {word for word in task_words if word}
    if not words or not body:
        return 0.0
    body_tokens = tokenize(body)
    if not body_tokens:
        return 0.0
    matches = sum(1 for word in words if word in body_tokens)
    return matches / len(words)


def combine_hidden_body_score(metadata_score: float, body_score: float) -> float:
    """Combina la similitud de metadata y el puntaje de cuerpo con pesos 0.5/0.5.

    Args:
        metadata_score: Similitud de la metadata (tipicamente 0.0-1.0).
        body_score: Puntaje del cuerpo (0.0-1.0).

    Returns:
        ``METADATA_WEIGHT * metadata_score + BODY_WEIGHT * body_score``.
    """
    return METADATA_WEIGHT * metadata_score + BODY_WEIGHT * body_score


def read_skill_body(path: str) -> str:
    """Lee el cuerpo de un skill/agente, prefiriendo la version ``.min.md``.

    Args:
        path: Ruta del ``.md`` del skill/agente (puede estar vacia).

    Returns:
        Contenido del ``.min.md`` si existe; si no, el del ``.md``; ``""`` si
        ninguno existe o la ruta es vacia. Nunca lanza.

    Raises:
        No aplica: los errores de I/O se capturan y degradan a ``""``.
    """
    if not path:
        return ""
    try:
        candidate = Path(path)
        min_candidate = candidate.with_suffix(".min.md")
        if min_candidate.exists():
            return min_candidate.read_text(encoding="utf-8")
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        logger.warning(
            "hidden_body: WHAT: no se pudo leer el cuerpo '%s': %s. "
            "WHY: archivo inaccesible, corrupto o ruta invalida. "
            "WHERE: read_skill_body",
            path,
            exc,
        )
    return ""
