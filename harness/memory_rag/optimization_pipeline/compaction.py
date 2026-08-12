"""Mixin de compactacion multi-pass para ``OptimizationPipeline``.

Extraido mecanicamente de ``optimization_pipeline.py`` (regla AGR < 500
lineas). Contiene el pipeline multi-etapa de compactacion con early
stopping (Microsoft Agent Framework 2026) y sus 4 stages.
"""
from __future__ import annotations

import logging

from ..context_window_manager import ContextWindow

logger = logging.getLogger("harness.memory_rag.optimization_pipeline")


class _CompactionPipelineMixin:
    """Multi-Pass Compaction Pipeline (Microsoft Agent Framework 2026)."""

    def _run_compaction_pipeline(
        self,
        window: ContextWindow,
        budget_target: int,
    ) -> ContextWindow:
        """
        Multi-Pass Compaction: aplica estrategias de compactacion en orden
        de agresividad creciente, con early stopping cuando se cumple el budget.

        Estrategias (TokenBudgetComposedStrategy de Microsoft):
          1. ToolResultCompaction   — observation masking (baja agresividad)
          2. SummarizationCompaction — resumir historia media (media)
          3. SlidingWindowCompaction — mantener ultimos N turns (alta)
          4. TruncationCompaction    — truncar tool outputs (maxima)

        Cada paso verifica si el budget esta satisfecho; si si, early stop.

        Args:
            window: ContextWindow a compactar.
            budget_target: Token target deseado.

        Returns:
            ContextWindow compactado (modificado in-place).
        """
        if not self._context_manager:
            return window

        stages = [
            ("ToolResultCompaction", self._stage_tool_result_compaction),
            ("SummarizationCompaction", self._stage_summarization_compaction),
            ("SlidingWindowCompaction", self._stage_sliding_window_compaction),
            ("TruncationCompaction", self._stage_truncation_compaction),
        ]

        for stage_name, stage_fn in stages:
            if window.total_tokens <= budget_target:
                logger.debug(
                    "Multi-pass: budget met (%d <= %d) after '%s', stopping",
                    window.total_tokens, budget_target, stage_name,
                )
                break
            stage_fn(window, budget_target)
            logger.debug(
                "Multi-pass: '%s' applied, tokens=%d/%d",
                stage_name, window.total_tokens, budget_target,
            )

        return window

    def _stage_tool_result_compaction(
        self, window: ContextWindow, target: int
    ) -> None:
        """
        Stage 1 — ToolResultCompaction (baja agresividad).

        Colapsa tool results usando Observation Masking: reemplaza contenido
        extenso de herramientas con placeholders [tool_output:{name}:{id}],
        preservando metadata y primeras 3 lineas.
        """
        tool_sec = window.get_section("tool_outputs")
        if tool_sec and not tool_sec.frozen and tool_sec.content:
            self._context_manager._compress_tool_outputs(tool_sec)  # type: ignore[private]

    def _stage_summarization_compaction(
        self, window: ContextWindow, target: int
    ) -> None:
        """
        Stage 2 — SummarizationCompaction (agresividad media).

        Resumela historia media de la conversacion si aun no se cumple el budget.
        """
        conv_sec = window.get_section("conversation_history")
        if conv_sec and not conv_sec.frozen and conv_sec.content:
            self._context_manager._summarize_conversation(conv_sec)  # type: ignore[private]

    def _stage_sliding_window_compaction(
        self, window: ContextWindow, target: int
    ) -> None:
        """
        Stage 3 — SlidingWindowCompaction (agresividad alta).

        Mantiene solo los ultimos N turns del historial de conversacion.
        """
        conv_sec = window.get_section("conversation_history")
        if conv_sec and not conv_sec.frozen and conv_sec.content:
            lines = conv_sec.content.split('\n\n')
            window_size = self._context_manager._sliding_window_size  # type: ignore[private]
            if len(lines) > window_size:
                keep = lines[-window_size:]
                conv_sec.content = '\n\n'.join(keep)
                conv_sec.compressed = True
                logger.debug(
                    "SlidingWindow: %d -> %d blocks",
                    len(lines), len(keep),
                )

    def _stage_truncation_compaction(
        self, window: ContextWindow, target: int
    ) -> None:
        """
        Stage 4 — TruncationCompaction (agresividad maxima).

        Trunca tool outputs al budget como ultimo recurso.
        """
        tool_sec = window.get_section("tool_outputs")
        if tool_sec and not tool_sec.frozen and tool_sec.over_budget:
            tool_sec.truncate_to_budget()
            logger.debug("TruncationCompaction: tool_outputs truncated to %d tokens", tool_sec.max_tokens)
