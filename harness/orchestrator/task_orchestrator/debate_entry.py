"""debate_entry.py — entrada de debate desde el flujo del ``TaskOrchestrator``.

WHAT: expone ``_DebateEntryMixin.run_debate_for_task``, el punto de entrada que
convierte una tarea en lenguaje natural en un debate real cuando el
``TaskPlanner`` marca la plantilla ``debate`` (``OrchestratorResult.is_debate``).
WHY: antes el flag ``is_debate`` quedaba sin efecto — se detectaba la plantilla
pero nadie invocaba ``TaskOrchestrator.run_debate``/``run_debate_async`` (gap de
integracion). WHERE: ``TaskOrchestrator`` por mixin (SRP; mantiene
``orchestrator.py`` por debajo del limite AGR de 500 lineas).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from harness.orchestrator.debate_orchestrator import DebateResult

logger = logging.getLogger("harness.orchestrator.task_orchestrator")


class _DebateEntryMixin:
    """Mixin con la entrada de debate invocable desde el flujo del planner."""

    async def run_debate_for_task(
        self,
        task: str,
        *,
        dispatch_fn: Callable[..., Any] | None = None,
    ) -> DebateResult | None:
        """Ejecuta el debate cuando la tarea activa la plantilla ``debate``.

        WHAT: procesa ``task`` con ``process_message`` (que resuelve el plan y
        el flag ``is_debate``); si la plantilla es ``debate`` invoca la ruta
        async nativa del debate (PaCoRe) con los agentes y la estrategia
        detectados; si no, devuelve ``None`` sin efectos. WHY: cierra el gap de
        integracion — el flag ``is_debate`` debe tener efecto real y no quedar
        solo como metadato. WHERE: call sites del orquestador (CLI/harness) que
        quieran materializar el debate.

        Args:
            task: Tarea en lenguaje natural.
            dispatch_fn: Callable opcional ``(agent, task, context) -> str`` para
                obtener respuestas reales. Si es ``None`` el debate usa el
                dispatch interno determinista.

        Returns:
            El ``DebateResult`` si la tarea es un debate; ``None`` si la
            plantilla no es ``debate`` (no se ejecuta ningun debate).

        Raises:
            ValueError: Si ``task`` esta vacia (propagado de
                ``DebateOrchestrator`` al ejecutar la estrategia).
        """
        result = await self.process_message(task)
        if not result.is_debate:
            plan = result.plan
            logger.info(
                "run_debate_for_task: plantilla '%s' no es debate; sin accion",
                plan.template_name if plan else "?",
            )
            return None

        agents = list(result.debate_agents)
        strategy = result.debate_strategy or "consensus"
        logger.info(
            "run_debate_for_task: invocando debate session=%s agents=%s strategy=%s",
            result.session_id, agents, strategy,
        )
        return await self.run_debate_async(
            session_id=result.session_id,
            task=result.original_message,
            agents=agents,
            strategy=strategy,
            dispatch_fn=dispatch_fn,
        )


__all__ = ["_DebateEntryMixin"]
