"""draft_review.py — Draft local + review cloud por complejidad (ADR-0084).

WHAT: Pipeline de 3 paths: SKIPPED (trivial: solo local, 0 tokens cloud),
VERIFY (medio: cloud acepta el draft bueno con pocos tokens) y ENHANCE
(duro o poca confianza: cloud parchea/regenera). Router de complejidad
inyectado + margen de confianza anti falsos-positivos.
WHY: Frontera — RLM-Cascade (arXiv:2606.22840): 88.8% draft-use, -45.8%
costo, 1.83x speedup, 100% vs 95% calidad; Local-Splitter T4 (51% en
RAG-heavy) + margen de confianza contra falsos positivos.
WHERE: Tras `LocalExecutor` para tareas no-triviales; el cloud supervisa,
no redacta desde cero (output tokens caros).

Uso:
    rev = DraftReviewer(draft_fn=ollama, review_fn=cloud, complexity_fn=router)
    out = rev.run("explica el modulo")  # out.path, out.output, out.cloud_tokens
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("harness.model_router.draft_review")

#: Path por defecto para tareas triviales (solo local).
DRAFT_PATH = "skipped"
#: Margen de confianza default: bajo esto se escala aunque sea trivial.
DEFAULT_CONFIDENCE_MARGIN = 0.5
#: Tokens cloud estimados de un VERIFY que acepta (prompt corto de check).
VERIFY_ACCEPT_TOKENS = 150


class ReviewPath(enum.Enum):
    """Path del pipeline (enum inmutable)."""

    SKIPPED = "skipped"
    VERIFY = "verify"
    ENHANCE = "enhance"


@dataclass(frozen=True)
class DraftOutcome:
    """Resultado del pipeline draft-review.

    Attributes:
        output: Texto final (draft aceptado o patch del cloud).
        path: Path tomado (SKIPPED/VERIFY/ENHANCE).
        cloud_tokens: Tokens cloud estimados (0 en SKIPPED).
    """

    output: str
    path: ReviewPath
    cloud_tokens: int


class DraftReviewer:
    """Pipeline draft-local + review-cloud con router de complejidad.

    Args:
        draft_fn: (task) -> (draft, confidence 0..1) en modelo local.
        review_fn: (task, draft) -> (final, accepted: bool) en cloud.
        complexity_fn: (task) -> "trivial"|"medium"|"hard".
        confidence_margin: Bajo esto se escala a ENHANCE aunque sea trivial.
    """

    def __init__(
        self,
        draft_fn: Callable[[str], tuple[str, float]],
        review_fn: Callable[[str, str], tuple[str, bool]],
        complexity_fn: Callable[[str], str],
        confidence_margin: float = DEFAULT_CONFIDENCE_MARGIN,
    ) -> None:
        """Inicializa el pipeline con funciones inyectadas (DI, testeable).

        Args:
            draft_fn: Generador local con confianza.
            review_fn: Revisor cloud (acepta o parchea).
            complexity_fn: Clasificador trivial/medium/hard.
            confidence_margin: Umbral anti falso-positivo.
        """
        self._draft_fn = draft_fn
        self._review_fn = review_fn
        self._complexity_fn = complexity_fn
        self._margin = confidence_margin

    def run(self, task: str) -> DraftOutcome:
        """Ejecuta el pipeline sobre la tarea.

        Orden: clasifica complejidad -> draft local con confianza ->
        SKIPPED si trivial+confiado; VERIFY si medio (acepta o parchea);
        ENHANCE si duro o poca confianza.

        Args:
            task: Descripcion de la tarea (no vacia).

        Returns:
            DraftOutcome con output, path y tokens cloud.

        Raises:
            ValueError: Si la tarea esta vacia (WHAT+WHY+WHERE).
        """
        if not task.strip():
            raise ValueError(
                "WHAT: tarea vacia. "
                "WHY: sin tarea no hay draft que generar. "
                "WHERE: DraftReviewer.run"
            )
        complexity = self._complexity_fn(task)
        draft, confidence = self._draft_fn(task)
        if complexity == "trivial" and confidence >= self._margin:
            logger.info("draft_review: SKIPPED (trivial confiado, 0 cloud)")
            return DraftOutcome(output=draft, path=ReviewPath.SKIPPED, cloud_tokens=0)
        if complexity == "medium" and confidence >= self._margin:
            final, accepted = self._review_fn(task, draft)
            if accepted:
                logger.info("draft_review: VERIFY aceptado (%d cloud)", VERIFY_ACCEPT_TOKENS)
                return DraftOutcome(
                    output=draft, path=ReviewPath.VERIFY,
                    cloud_tokens=VERIFY_ACCEPT_TOKENS,
                )
        final, _accepted = self._review_fn(task, draft)
        logger.info("draft_review: ENHANCE (cloud parchea)")
        return DraftOutcome(
            output=final, path=ReviewPath.ENHANCE,
            cloud_tokens=len(final) // 4 + VERIFY_ACCEPT_TOKENS,
        )
