"""cross_review.py — Revision cruzada forzada entre familias (Search 9-13, ADR-0081).

WHAT: Asigna un revisor de familia DISTINTA al escritor (Claude->GPT/Ollama);
con preferencia por revisor local (0 tokens cloud). Registra el par.
WHY: Frontera — "si codifico con Claude Code, lo envio a GPT para revision:
diferentes perspectivas encuentran distintos problemas"; la auto-revision
ciega los mismos blind-spots.
WHERE: `parallel_executor` tras generar codigo, antes de PBT/mutacion.

Uso:
    pair = CrossReviewer().assign("claude-opus", ["claude-haiku","gpt-4o","qwen3:4b"])
    # pair.reviewer_family in {"gpt","ollama"} (nunca "claude")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("harness.validation.cross_review")

#: Familia por prefijo de modelo (orden: especifico antes que generico).
FAMILY_MAP: dict[str, str] = {
    "claude": "claude",
    "gpt": "gpt",
    "o1": "gpt",
    "o3": "gpt",
    "qwen": "ollama",
    "deepseek": "ollama",
    "llama": "ollama",
    "mistral": "ollama",
}


def model_family(model: str) -> str:
    """Detecta la familia de un modelo por prefijo (case-insensitive).

    Args:
        model: Nombre del modelo (p. ej. "claude-opus", "qwen3:4b").

    Returns:
        Familia ("claude"|"gpt"|"ollama"|...) o "unknown".
    """
    lowered = model.lower()
    for prefix, family in FAMILY_MAP.items():
        if lowered.startswith(prefix) or f"/{prefix}" in lowered or f":{prefix}" in lowered:
            return family
    return "unknown"


def _is_local(model: str) -> bool:
    """True si el modelo es local (Ollama: qwen/deepseek/llama/mistral).

    Args:
        model: Nombre del modelo.

    Returns:
        True si corre en local (0 tokens cloud).
    """
    return model_family(model) == "ollama"


@dataclass(frozen=True)
class ReviewPair:
    """Par escritor->revisor asignado.

    Attributes:
        writer: Modelo escritor.
        reviewer: Modelo revisor (familia distinta).
        writer_family: Familia del escritor.
        reviewer_family: Familia del revisor.
    """

    writer: str
    reviewer: str
    writer_family: str
    reviewer_family: str


def assign_reviewer(writer: str, available: list[str]) -> str:
    """Asigna un revisor de familia distinta (prefiere local).

    Args:
        writer: Modelo que escribio el codigo.
        available: Modelos candidatos a revisor.

    Returns:
        Nombre del revisor (familia != escritor; local primero).

    Raises:
        ValueError: Si no hay candidato de otra familia (no auto-revision).
    """
    writer_family = model_family(writer)
    others = [m for m in available if model_family(m) != writer_family]
    if not others:
        raise ValueError(
            f"WHAT: sin revisor de otra familia para '{writer}' (familia {writer_family}). "
            "WHY: la auto-revision ciega los mismos blind-spots; se exige "
            "perspectiva distinta. "
            "WHERE: assign_reviewer"
        )
    locals_first = sorted(others, key=lambda m: (not _is_local(m), m))
    chosen = locals_first[0]
    logger.info(
        "cross_review: escritor %s (%s) -> revisor %s (%s)",
        writer, writer_family, chosen, model_family(chosen),
    )
    return chosen


class CrossReviewer:
    """Asignador con registro de pares (auditoria)."""

    def __init__(self) -> None:
        """Inicializa el historial vacio de pares."""
        self._pairs: list[ReviewPair] = []

    @property
    def pairs(self) -> tuple[ReviewPair, ...]:
        """Pares asignados (tupla inmutable)."""
        return tuple(self._pairs)

    def assign(self, writer: str, available: list[str]) -> ReviewPair:
        """Asigna y registra el par escritor->revisor.

        Args:
            writer: Modelo escritor.
            available: Candidatos a revisor.

        Returns:
            ReviewPair registrado.
        """
        reviewer = assign_reviewer(writer, available)
        pair = ReviewPair(
            writer=writer,
            reviewer=reviewer,
            writer_family=model_family(writer),
            reviewer_family=model_family(reviewer),
        )
        self._pairs.append(pair)
        return pair
