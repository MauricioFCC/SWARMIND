"""fanout_gate.py — Anti-sobre-descomposicion (ADR-0075).

WHAT: Gate de 1 linea que decide si el fan-out multi-agente vale la pena:
si el baseline single-agent ya logra >= 80% de exito, descomponer ANADE
ruido (redes no estructuradas amplifican errores hasta 17.2x).
WHY: Frontera (Minitap/AndroidWorld arXiv:2602.07787 + EECS-2026-123) —
la descomposicion no estructurada amplifica errores; el fan-out solo paga
cuando el baseline es debil.
WHERE: Antes del ParallelExecutor/orchestrator: probe de 1 pasada y gate.

Uso:
    if should_fanout(baseline_success=0.55) is FanoutDecision.FANOUT:
        ejecutar_fan_out()
"""

from __future__ import annotations

import enum
import logging

logger = logging.getLogger("harness.orchestrator.fanout_gate")

#: Umbral single-agent (frontera Minitap): >= 80% -> no fan-out.
SINGLE_AGENT_THRESHOLD = 0.8
#: Amplificacion de ruido de redes no estructuradas (frontera, x17.2).
FANOUT_NOISE_AMPLIFICATION = 17.2


class FanoutDecision(enum.Enum):
    """Decision del gate (enum inmutable)."""

    FANOUT = "fanout"
    SINGLE = "single"


def should_fanout(baseline_success: float, force: bool = False) -> FanoutDecision:
    """Decide si el fan-out multi-agente vale la pena.

    Args:
        baseline_success: Success rate del probe single-agent (1 pasada),
            en [0, 1].
        force: True fuerza FANOUT aunque el baseline sea fuerte (escape
            hatch del operador).

    Returns:
        FanoutDecision.FANOUT si el baseline es debil (< umbral) o force;
        FanoutDecision.SINGLE si el baseline ya es fuerte.

    Raises:
        ValueError: Si baseline_success no esta en [0, 1] (WHAT+WHY+WHERE).
    """
    if not (0.0 <= baseline_success <= 1.0):
        raise ValueError(
            f"WHAT: baseline_success invalido: {baseline_success}. "
            "WHY: es un success rate, debe estar en [0, 1]. "
            "WHERE: should_fanout"
        )
    if force or baseline_success < SINGLE_AGENT_THRESHOLD:
        if baseline_success >= SINGLE_AGENT_THRESHOLD:
            logger.info("fanout_gate: force=True vence al baseline fuerte")
        return FanoutDecision.FANOUT
    logger.info(
        "fanout_gate: baseline %.0f%% >= %.0f%%; single-agent (evita ruido x%.1f)",
        baseline_success * 100,
        SINGLE_AGENT_THRESHOLD * 100,
        FANOUT_NOISE_AMPLIFICATION,
    )
    return FanoutDecision.SINGLE
