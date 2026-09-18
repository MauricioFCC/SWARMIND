"""sprt_governor.py — Gobernador SPRT: parada por score-juez + cap duro (ADR-0087).

WHAT: Acumula scores de juez por ronda; STOP al cruzar el umbral o al
agotar max_rounds. El juez que no discrimina (scores planos) es senal de
tarea facil o juez inutil, no de exito.
WHY: Morandi (arXiv 2605.19193): GSM8K 97% con 4.06 llamadas vs 99% con
15 (-2pp a 3.7x menos costo); parada = score + umbral calibrado + cap.
WHERE: Rondas R1-R2 de la mesa adversarial; loops verify-replan.

Uso:
    gov = SPRTGovernor(threshold=0.8, max_rounds=2)
    if gov.observe(score) is GovernorDecision.STOP: sintetizar()
"""

from __future__ import annotations

import enum
import logging

logger = logging.getLogger("harness.orchestrator.sprt_governor")


class GovernorDecision(enum.Enum):
    """Decision del gobernador (enum inmutable)."""

    CONTINUE = "continue"
    STOP = "stop"


class SPRTGovernor:
    """Gobernador secuencial de rondas con umbral y cap duro.

    Args:
        threshold: Score [0,1] que detiene (calibrado por dominio).
        max_rounds: Cap duro de rondas.
    """

    def __init__(self, threshold: float, max_rounds: int) -> None:
        """Inicializa el gobernador validando la configuracion.

        Args:
            threshold: Umbral en (0, 1).
            max_rounds: Cap >= 1.

        Raises:
            ValueError: Si la config es invalida (WHAT+WHY+WHERE).
        """
        if not (0.0 < threshold < 1.0):
            raise ValueError(
                f"WHAT: threshold invalido: {threshold}. "
                "WHY: debe estar en (0, 1) para discriminar scores. "
                "WHERE: SPRTGovernor.__init__"
            )
        if max_rounds < 1:
            raise ValueError(
                f"WHAT: max_rounds invalido: {max_rounds}. "
                "WHY: se necesita al menos 1 ronda. "
                "WHERE: SPRTGovernor.__init__"
            )
        self._threshold = threshold
        self._max_rounds = max_rounds
        self._rounds = 0

    def observe(self, score: float) -> GovernorDecision:
        """Registra el score de la ronda y decide.

        Args:
            score: Score del juez [0, 1] de la ronda.

        Returns:
            STOP si score >= umbral o se agoto el cap; CONTINUE si no.
        """
        self._rounds += 1
        if score >= self._threshold:
            logger.info("sprt_governor: STOP por umbral (%.2f >= %.2f)", score, self._threshold)
            return GovernorDecision.STOP
        if self._rounds >= self._max_rounds:
            logger.info("sprt_governor: STOP por cap (%d rondas)", self._max_rounds)
            return GovernorDecision.STOP
        return GovernorDecision.CONTINUE
