"""rag_evaluator.py — Regla de las 20 preguntas (Search 9-13, ADR-0081).

WHAT: Suite fija de 20 preguntas representativas del dominio; cada una se
clasifica en OK o en un tipo de fallo: RETRIEVAL (sin docs), MODEL_IGNORED
(responde sin usar la evidencia) o WRONG_TOOL (placeholder para wiring con
telemetria de tools).
WHY: Frontera — "haz 20 preguntas representativas; entiende por que acierta
o falla cada una; eso ensena mas que todos los logotipos"; anadir
complejidad solo si el fallo lo justifica.
WHERE: Antes de aprobar cambios al pipeline Hybrid/CorrectiveRetriever.

Uso:
    summary = evaluate_suite(RAG_QUESTIONS, retriever_fn, model_fn)
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger("harness.memory_rag.rag_evaluator")

#: Las 20 preguntas representativas (dominio: el propio harness SWARMIND).
RAG_QUESTIONS: tuple[str, ...] = (
    "quien decide el tier del modelo en el router",
    "como se evita el doble efecto en retries",
    "que hace el gate de votacion gobernada",
    "donde se registra un fallo para distilarlo en skill",
    "como se reancla el contexto tras una compaction",
    "que tiers de skills existen y cual es el maximo installed",
    "como se detecta un cache-buster estructural",
    "que hace la cascada STEER cuando la confianza es baja",
    "como se valida un JSON contra su schema con retries",
    "que modelos locales estan registrados en opencode",
    "como se delega una tarea a un subagente con least privilege",
    "que pasa si un mutante sobrevive a la suite",
    "como se mide la eficiencia por modelo en tokens por llamada",
    "que hace el prune de tool results antes de compactar",
    "como se podan pares conflictivos de skills",
    "que decide el fanout gate con baseline fuerte",
    "como se exporta una traza para replay sin LLM",
    "que checklist exige el spec antes de codear",
    "como se asigna un revisor de otra familia",
    "que excluye el backup a Google Drive por defecto",
)


class FailureKind(enum.Enum):
    """Tipo de fallo de una pregunta (enum inmutable)."""

    NONE = "none"
    RETRIEVAL = "retrieval"
    MODEL_IGNORED = "model_ignored"
    WRONG_TOOL = "wrong_tool"


@dataclass(frozen=True)
class QuestionOutcome:
    """Resultado de evaluar una pregunta.

    Attributes:
        question: Pregunta evaluada.
        failure: Tipo de fallo (NONE si OK).
        retrieved: Docs recuperados (tupla).
    """

    question: str
    failure: FailureKind
    retrieved: tuple[str, ...]


@dataclass
class SuiteSummary:
    """Agregado de la suite (mutable durante la evaluacion)."""

    total: int = 0
    by_kind: dict = field(default_factory=dict)

    def add(self, outcome: QuestionOutcome) -> None:
        """Acumula un resultado.

        Args:
            outcome: Resultado de una pregunta.
        """
        self.total += 1
        self.by_kind[outcome.failure] = self.by_kind.get(outcome.failure, 0) + 1


def _shares_terms(answer: str, docs: list[str]) -> bool:
    """True si la respuesta comparte >= 2 terminos con la evidencia.

    Args:
        answer: Respuesta del modelo (lowercase ya aplicado por caller).
        docs: Documentos recuperados.

    Returns:
        True si hay solapamiento lexico significativo.
    """
    stop = {"el", "la", "los", "las", "de", "en", "y", "que", "con", "para", "un", "una"}
    terms = {w for w in answer.split() if len(w) > 3 and w not in stop}
    evidence = " ".join(docs).lower()
    return sum(1 for t in terms if t in evidence) >= 2


def evaluate_question(
    question: str,
    retriever_fn: Callable[[str], list[str]],
    model_answer: str = "",
) -> QuestionOutcome:
    """Evalua una pregunta y clasifica su fallo.

    Args:
        question: Pregunta representativa (no vacia).
        retriever_fn: (query) -> docs recuperados.
        model_answer: Respuesta del modelo ("" = sin modelo; si hay docs
            pero no respuesta, se asume que el modelo la usaria -> OK).

    Returns:
        QuestionOutcome con el tipo de fallo.

    Raises:
        ValueError: Si la pregunta esta vacia (WHAT+WHY+WHERE).
    """
    if not question.strip():
        raise ValueError(
            "WHAT: pregunta vacia. "
            "WHY: sin pregunta no hay evaluacion. "
            "WHERE: evaluate_question"
        )
    docs = retriever_fn(question)
    if not docs:
        return QuestionOutcome(question, FailureKind.RETRIEVAL, ())
    if model_answer and not _shares_terms(model_answer.lower(), docs):
        return QuestionOutcome(question, FailureKind.MODEL_IGNORED, tuple(docs))
    return QuestionOutcome(question, FailureKind.NONE, tuple(docs))


def evaluate_suite(
    questions: list[str] | tuple[str, ...],
    retriever_fn: Callable[[str], list[str]],
    model_fn: Callable[[str], str] | None = None,
) -> SuiteSummary:
    """Evalua la suite completa y agrega por tipo de fallo.

    Args:
        questions: Preguntas a evaluar.
        retriever_fn: (query) -> docs.
        model_fn: (question) -> respuesta; None = sin modelo (solo retrieval).

    Returns:
        SuiteSummary con total y conteos por FailureKind.
    """
    summary = SuiteSummary()
    for question in questions:
        answer = model_fn(question) if model_fn is not None else ""
        summary.add(evaluate_question(question, retriever_fn, answer))
    logger.info(
        "rag_evaluator: %d preguntas, fallos=%s",
        summary.total, {k.value: v for k, v in summary.by_kind.items()},
    )
    return summary
