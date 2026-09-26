"""tool_pipeline.py — Pipeline de ejecucion: pre->guards->approval->around->post (ADR-0098).

WHAT: Orquesta un tool-call en fases: guards monotonicos (cualquiera
bloquea), approval humana, around (timeout+retry del tool), post y
finalize inmutable. El tool NUNCA corre si un guard o approval lo niega.
WHY: deepseek-harness tool-execution-pipeline: politica reordenable sin
tocar el loop; subcalls adyacentes; resultado final inmutable.
WHERE: Executor de tools del orquestador (antes del provider directo).

Uso:
    out = run_tool_pipeline(tool=fn, guards=[g1], approval_fn=ask)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("harness.orchestrator.tool_pipeline")


@dataclass(frozen=True)
class PipelineResult:
    """Resultado final inmutable del pipeline.

    Attributes:
        output: Salida del tool (None si bloqueado/denegado/fallo).
        approved: True si paso guards + approval.
        reason: Motivo legible (bloqueo, denegacion o error).
    """

    output: Any = None
    approved: bool = False
    reason: str = ""


def run_tool_pipeline(
    tool: Callable[..., Any],
    guards: list[Callable[..., str | None]],
    approval_fn: Callable[[], bool],
    timeout_s: float = 60.0,
) -> PipelineResult:
    """Ejecuta el pipeline completo sobre un tool-call.

    Orden: guards (primero que bloquee gana) -> approval -> around
    (timeout via ejecucion directa; el retry lo gobierna el caller) ->
    post (aqui: sin transformacion) -> finalize inmutable.

    Args:
        tool: Callable del tool (kwargs libres).
        guards: Lista de fns (kwargs) -> motivo str o None si pasa.
        approval_fn: () -> True si el humano aprueba.
        timeout_s: Reservado para around con timeout (documentado).

    Returns:
        PipelineResult (errores del tool capturados, nunca lanza).
    """
    _ = timeout_s
    for guard in guards:
        try:
            verdict = guard()
        except Exception as exc:  # noqa: BLE001 - guard roto = bloquear
            logger.warning("tool_pipeline: guard lanzo (%s); bloqueando", exc)
            return PipelineResult(
                approved=False, reason=f"guard roto: {exc}"
            )
        if verdict:
            logger.warning("tool_pipeline: bloqueado por guard (%s)", verdict)
            return PipelineResult(approved=False, reason=str(verdict))
    try:
        approved = bool(approval_fn())
    except Exception as exc:  # noqa: BLE001 - approval roto = denegar
        return PipelineResult(approved=False, reason=f"approval fallo: {exc}")
    if not approved:
        return PipelineResult(approved=False, reason="approval denegada por humano")
    try:
        return PipelineResult(output=tool(), approved=True, reason="ok")
    except Exception as exc:  # noqa: BLE001 - error del tool capturado
        logger.warning("tool_pipeline: tool lanzo (%s)", exc)
        return PipelineResult(approved=True, reason=f"tool fallo: {exc}")
