"""verify_replan_gate.py — Gate Plan-Execute-Verify-Replan (ADR-0079, VMAO ICLR26).

WHAT: Evalua si un plan continua (REPLAN) o se detiene (STOP): stop si
>= 80% completo, o si confianza >= 75% con >= 50% completo.
WHY: VMAO 2026 — el loop verify->replan con esos umbrales evita iterar
sobre planes casi-listos (tokens Exec 61%/Verify 16%/Synthesis 10%);
seguir replaneando pasado el umbral es waste puro.
WHERE: `task_planner`/`adaptive_planner` tras cada fase de verificacion.

Uso:
    gate = VerifyReplanGate()
    out = gate.evaluate(completion=0.85, confidence=0.6)
    if out.stop: sintetizar()
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass

logger = logging.getLogger("harness.orchestrator.verify_replan_gate")

#: Umbral STOP por completitud (VMAO).
STOP_COMPLETE = 0.8
#: Umbral STOP combinado (confianza, completitud) (VMAO).
STOP_CONF_COMPLETE: tuple[float, float] = (0.75, 0.5)


class GateDecision(enum.Enum):
    """Decision del gate (enum inmutable)."""

    REPLAN = "replan"
    STOP = "stop"


@dataclass(frozen=True)
class GateOutcome:
    """Resultado de evaluar el gate.

    Attributes:
        decision: REPLAN (seguir) o STOP (sintetizar).
        stop: True si hay que detenerse.
        reason: Motivo legible con los umbrales aplicados.
    """

    decision: GateDecision
    stop: bool
    reason: str


def _check_unit(name: str, value: float) -> None:
    """Valida un ratio en [0, 1] (WHAT+WHY+WHERE).

    Args:
        name: Nombre del parametro (para el mensaje).
        value: Valor a validar.

    Raises:
        ValueError: Si esta fuera de [0, 1].
    """
    if not (0.0 <= value <= 1.0):
        raise ValueError(
            f"WHAT: {name} invalido: {value}. "
            "WHY: es un ratio, debe estar en [0, 1]. "
            "WHERE: VerifyReplanGate.evaluate"
        )


class VerifyReplanGate:
    """Gate VMAO: STOP si el plan esta suficiente, REPLAN si no."""

    def evaluate(self, completion: float, confidence: float) -> GateOutcome:
        """Evalua completitud y confianza contra los umbrales VMAO.

        Args:
            completion: Fraccion del plan completada [0, 1].
            confidence: Confianza en lo completado [0, 1].

        Returns:
            GateOutcome con decision y motivo.

        Raises:
            ValueError: Si algun input esta fuera de [0, 1].
        """
        _check_unit("completion", completion)
        _check_unit("confidence", confidence)
        conf_thr, comp_thr = STOP_CONF_COMPLETE
        if completion >= STOP_COMPLETE:
            reason = f"completitud {completion:.2f} >= {STOP_COMPLETE:.2f} (VMAO)"
            logger.info("verify_replan_gate: STOP (%s)", reason)
            return GateOutcome(GateDecision.STOP, True, reason)
        if confidence >= conf_thr and completion >= comp_thr:
            reason = (
                f"confianza {confidence:.2f} >= {conf_thr:.2f} y completitud "
                f"{completion:.2f} >= {comp_thr:.2f} (VMAO)"
            )
            logger.info("verify_replan_gate: STOP (%s)", reason)
            return GateOutcome(GateDecision.STOP, True, reason)
        reason = (
            f"completitud {completion:.2f} < {STOP_COMPLETE:.2f} y "
            f"(confianza {confidence:.2f} < {conf_thr:.2f} o completitud "
            f"< {comp_thr:.2f}): replanificar (VMAO)"
        )
        return GateOutcome(GateDecision.REPLAN, False, reason)
