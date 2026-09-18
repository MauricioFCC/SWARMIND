"""content_restrictor.py — Restrictor markdown organico (ADR-0088, SerpApi).

WHAT: Si el input es JSON de buscador (organic/ads/pagination/related),
extrae SOLO el contenido organico a markdown; si ya es markdown, limpieza
minima. Reduce tokens manteniendo la senal.
WHY: SerpApi: JSON 24.7k -> md 6.4k tokens (-74%; solo organic -95%).
El modelo lee, no parsea: darle JSON con ads es pagar ruido.
WHERE: `webfetch`/RAG antes de inyectar resultados al contexto.

Uso:
    md = restrict_markdown(raw_json_or_markdown)
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger("harness.orchestrator.content_restrictor")

#: Claves JSON consideradas ruido (no organicas).
_NOISE_KEYS: frozenset[str] = frozenset({
    "ads", "sponsored", "pagination", "related", "related_searches",
    "metadata", "debug", "timing", "credits", "facets",
})

#: Claves JSON con contenido organico.
_ORGANIC_KEYS: frozenset[str] = frozenset({
    "organic", "results", "items", "answer", "snippet",
})


def _organic_markdown(data: object) -> str:
    """Extrae texto organico de un JSON (recursivo, sin ruido).

    Args:
        data: Objeto parseado (dict/list/str).

    Returns:
        Texto organico concatenado.
    """
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, list):
        parts = [_organic_markdown(item) for item in data]
        return "\n".join(p for p in parts if p)
    if isinstance(data, dict):
        chunks: list[str] = []
        for key, value in data.items():
            if key in _NOISE_KEYS:
                continue
            if key in _ORGANIC_KEYS or isinstance(value, (dict, list)):
                text = _organic_markdown(value)
                if text:
                    chunks.append(text)
            elif isinstance(value, str) and value.strip():
                chunks.append(value.strip())
        return "\n".join(chunks)
    return ""


def restrict_markdown(raw: str) -> str:
    """Restringe contenido a markdown organico ( SerpApi-style).

    Args:
        raw: JSON de buscador o markdown (no vacio).

    Returns:
        Markdown solo-organico (o el texto limpio si no era JSON).

    Raises:
        ValueError: Si el input esta vacio (WHAT+WHY+WHERE).
    """
    if not raw.strip():
        raise ValueError(
            "WHAT: contenido vacio. "
            "WHY: sin contenido no hay nada que restringir. "
            "WHERE: restrict_markdown"
        )
    text = raw.strip()
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if data is not None:
            organic = _organic_markdown(data)
            if organic:
                logger.info(
                    "content_restrictor: %d -> %d chars (organico)",
                    len(raw), len(organic),
                )
                return organic
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    return cleaned
