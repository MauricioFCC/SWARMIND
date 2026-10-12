"""triage_slm.py — Triage con SLM + cascada determinista a DifficultyRouter.

WHAT: clasifica una tarea en ``{intent, complexity(1-5)}`` usando un small
model inyectado (DI) y, ante excepcion, JSON invalido o valor fuera de rango,
cae a ``DifficultyRouter`` (heuristica pura). WHY: el routing se aprende con un
clasificador barato + evidencia; la cascada evita que un fallo del SLM bloquee
el pipeline (frontera 2026). WHERE: coordinator / DifficultyRouter (ADR-0103,
FR-C1, WS-C).

NF-3 (determinismo): ``fallback`` es determinista y nunca lanza.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from harness.common import safe_json_loads
from harness.orchestrator.difficulty_router import (
    ComplexityLevel,
    DifficultyRouter,
)

logger = logging.getLogger(__name__)

#: Rango valido de complejidad (int).
MIN_COMPLEXITY = 1
MAX_COMPLEXITY = 5

#: Traduccion ``ComplexityLevel`` -> escala 1..5 usada por ``TriageResult``.
_LEVEL_TO_INT: dict[ComplexityLevel, int] = {
    ComplexityLevel.TRIVIAL: 1,
    ComplexityLevel.SIMPLE: 2,
    ComplexityLevel.MODERATE: 3,
    ComplexityLevel.COMPLEX: 4,
    ComplexityLevel.VERY_COMPLEX: 5,
}

#: Complejidad de reserva si el propio fallback no puede clasificar.
_FALLBACK_COMPLEXITY = 3


@dataclass(frozen=True)
class TriageResult:
    """Resultado del triage.

    Attributes:
        intent: Categoria/intencion detectada (no vacia).
        complexity: Complejidad en el rango 1..5.
        raw: JSON crudo devuelto por el small model (``""`` en el fallback).
    """

    intent: str
    complexity: int
    raw: str


class TriageSLM:
    """Triage con small model inyectado y fallback determinista.

    Uso:
        triage = TriageSLM(small_model_callable=llm_json)
        result = triage.triage("implementar API REST")
        # result.intent, result.complexity(1-5), result.raw
    """

    def __init__(
        self, *, small_model_callable: Callable[[str], object] | None = None
    ) -> None:
        """Inicializa el triage con un small model opcional.

        Args:
            small_model_callable: Callable ``text -> JSON`` (``str`` o ``dict``)
                que produce ``{"intent": <str>, "complexity": <1-5>}``. Si es
                ``None``, todo ``triage`` delega en ``fallback``.
        """
        self._small_model_callable = small_model_callable
        self._difficulty_router = DifficultyRouter()

    def triage(self, text: str) -> TriageResult:
        """Clasifica ``text`` con el SLM y cae al fallback ante cualquier fallo.

        Args:
            text: Tarea del usuario.

        Returns:
            ``TriageResult`` siempre valido (nunca lanza; ante fallo usa
            :meth:`fallback`).
        """
        if self._small_model_callable is None:
            return self.fallback(text)

        try:
            raw = self._small_model_callable(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "triage_slm: WHAT: el small model fallo: %s. "
                "WHY: excepcion/timeout del SLM. WHERE: TriageSLM.triage",
                exc,
            )
            return self.fallback(text)

        parsed = safe_json_loads(raw, default=None)
        intent = parsed.get("intent") if isinstance(parsed, dict) else None
        complexity = parsed.get("complexity") if isinstance(parsed, dict) else None

        if (
            not isinstance(intent, str)
            or not intent.strip()
            or not isinstance(complexity, int)
            or isinstance(complexity, bool)
            or not MIN_COMPLEXITY <= complexity <= MAX_COMPLEXITY
        ):
            logger.warning(
                "triage_slm: WHAT: respuesta invalida del SLM (%r). "
                "WHY: falta intent/complexity o complejidad fuera de 1..5. "
                "WHERE: TriageSLM.triage",
                raw if isinstance(raw, str) else type(raw).__name__,
            )
            return self.fallback(text)

        raw_text = raw if isinstance(raw, str) else ""
        return TriageResult(intent=intent.strip(), complexity=complexity, raw=raw_text)

    def fallback(self, text: str) -> TriageResult:
        """Clasifica con ``DifficultyRouter`` (cascada determinista, no lanza).

        Args:
            text: Tarea del usuario (puede ser vacia).

        Returns:
            ``TriageResult`` traducido desde ``ComplexityLevel`` a 1..5; si el
            router falla, una complejidad de reserva valida.
        """
        try:
            decision = self._difficulty_router.route(text or "")
            level = decision.complexity
            complexity = _LEVEL_TO_INT.get(level, _FALLBACK_COMPLEXITY)
            intent = level.value if isinstance(level, ComplexityLevel) else str(level)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "triage_slm: WHAT: fallback DifficultyRouter fallo: %s. "
                "WHY: heuristica no disponible o entrada invalida. "
                "WHERE: TriageSLM.fallback",
                exc,
            )
            return TriageResult(
                intent=ComplexityLevel.MODERATE.value,
                complexity=_FALLBACK_COMPLEXITY,
                raw="",
            )
        return TriageResult(intent=intent, complexity=complexity, raw="")
