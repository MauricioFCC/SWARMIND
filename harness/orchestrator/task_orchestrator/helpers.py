"""Helpers de Composition Root — enable_cache / enable_golden_signals / etc.

Extracción mecánica desde ``harness/orchestrator/task_orchestrator.py``
(sin cambios de lógica).
"""

from __future__ import annotations

import asyncio

from harness.orchestrator.orchestration_result import OrchestratorResult
from harness.orchestrator.structured_log import StructuredLogRecord

from .orchestrator import TaskOrchestrator


def enable_cache(orchestrator: TaskOrchestrator, max_tokens: int = 50000) -> None:
    """Habilitar ShapedCache en TaskOrchestrator (ADR-0018 Token Economics)."""
    from harness.memory_rag.semantic_cache import SemanticCache, ShapedCache
    orchestrator._shaped_cache = ShapedCache(semantic_cache=SemanticCache(), max_tokens=max_tokens)
    StructuredLogRecord.info(
        "cache_enabled", message=f"ShapedCache activado: max_tokens={max_tokens}",
        session_id="", **(orchestrator._shaped_cache.get_stats()),
    )


def enable_golden_signals(orchestrator: TaskOrchestrator, **kwargs) -> None:
    """Habilitar Golden Signals LLM en el tracker de telemetria (ADR-0034).

    Expone latencia (p50/p95/p99), costo por tarea y hit-rate de cache en
    el resumen exportado por TelemetryTracker. Composition Root.

    Args:
        orchestrator: instancia activa de TaskOrchestrator.
        **kwargs: parametros de costo para GoldenSignals
            (cost_input_per_1k, cost_output_per_1k, cache_read_discount).
    """
    if orchestrator._telemetry is None:
        StructuredLogRecord.warning(
            "golden_signals_skipped",
            message="TaskOrchestrator no tiene telemetria habilitada; "
                    "Golden Signals no activado",
            session_id="",
        )
        return
    orchestrator._telemetry.enable_golden_signals(**kwargs)
    StructuredLogRecord.info(
        "golden_signals_enabled",
        message="Golden Signals LLM activados en telemetria",
        session_id="",
    )


def enable_speculative_tools(orchestrator: TaskOrchestrator, **kwargs) -> None:
    """Habilitar Speculative Tool Execution (ADR-0034).

    Predice patrones de llamadas a herramientas y las ejecuta en paralelo
    (dry-run) mientras el LLM genera, confirmando solo las acertadas.

    Args:
        orchestrator: instancia activa de TaskOrchestrator.
        **kwargs: argumentos para SpeculativeToolExecutor
            (eligible_tools, dry_run).
    """
    from harness.orchestrator.speculative_tool_exec import SpeculativeToolExecutor
    orchestrator._speculative_executor = SpeculativeToolExecutor(**kwargs)
    StructuredLogRecord.info(
        "speculative_tools_enabled",
        message="Speculative Tool Execution activada",
        session_id="",
    )


def run_process_message(orchestrator: TaskOrchestrator, message: str, force_agent: str | None = None) -> OrchestratorResult:
    """Ejecutar process_message sincrono (wrapper asyncio.run)."""
    return asyncio.run(orchestrator.process_message(message, force_agent=force_agent))
