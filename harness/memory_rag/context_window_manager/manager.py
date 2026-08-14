"""Gestor de ventana de contexto para el paquete ``context_window_manager``.

Extraido mecanicamente de ``context_window_manager.py`` (regla AGR < 500
lineas). Contiene ``ContextWindowManager``, el gestor principal que
orquesta truncado, summarization, observation masking y dropping.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from harness.common import CHARS_PER_TOKEN, StatsMixin, compression_pct
from harness.memory_rag.context_compression import (
    aggressive_compress,
    compress_tool_outputs,
    hard_truncate,
    summarize_conversation,
    summarize_messages,
)

from .constants import PRIORITY_LOW, SLIDING_WINDOW_SIZE
from .estimator import TokenEstimator
from .sections import ContextSection
from .window import ContextWindow

logger = logging.getLogger("harness.memory_rag.context_window_manager")


# ---------------------------------------------------------------------------
# Context Window Manager
# ---------------------------------------------------------------------------

class ContextWindowManager(StatsMixin):
    """Gestiona la ventana de contexto para llamadas LLM.

    Estrategias:
      1. Priority ordering: secciones criticas primero, fondo despues
      2. Budget allocation: cada seccion tiene un maximo de tokens
      3. Sliding window: mantener ultimos N mensajes completos
      4. Summarization: comprimir historial antiguo a resumen
      5. Section dropping: eliminar secciones de baja prioridad si es necesario
      6. Observation Masking: reemplazar tool outputs grandes con placeholders

    Uso:
        cwm = ContextWindowManager(total_budget=12000)
        window = cwm.create_window()
        window.add_section("system_identity", "You are...", frozen=True)
        window.add_section("rag_context", "...", max_tokens=2000)
        optimized = cwm.optimize(window)
        prompt = optimized.to_prompt()
    """

    def __init__(
        self,
        total_budget: int = 12000,
        sliding_window_size: int = SLIDING_WINDOW_SIZE,
        summary_fn: Callable[[str], str] | None = None,
        model_family: str = "claude",
        use_real_tokenizer: bool = True,
        use_observation_masking: bool = True,
    ) -> None:
        """Inicializa el gestor de ventana de contexto.

        Args:
            total_budget: Tokens maximos para la ventana completa.
            sliding_window_size: Mensajes completos a mantener.
            summary_fn: Funcion de resumen personalizada.
            model_family: Familia de modelo para TokenEstimator.
            use_real_tokenizer: Usar tokenizador real (tiktoken) si esta disponible.
            use_observation_masking: Usar Observation Masking en tool outputs.
        """
        super().__init__()
        self._total_budget = total_budget
        self._sliding_window_size = sliding_window_size
        self._summary_fn = summary_fn or summarize_messages
        self._use_real_tokenizer = use_real_tokenizer
        self._use_observation_masking = use_observation_masking

        self._token_estimator = TokenEstimator(model_family=model_family)

        self._stats: dict[str, Any] = {
            "optimizations": 0,
            "truncations": 0,
            "summarizations": 0,
            "sections_dropped": 0,
            "tokens_before": 0,
            "tokens_after": 0,
            "tokens_saved": 0,
        }

        logger.info(
            "ContextWindowManager initialized (budget=%d, sliding=%d, "
            "model=%s, real_tokenizer=%s, obs_mask=%s)",
            total_budget, sliding_window_size,
            model_family, use_real_tokenizer, use_observation_masking,
        )

    # ------------------------------------------------------------------
    # Helpers de tokenizacion
    # ------------------------------------------------------------------

    def _count_tokens(self, text: str) -> int:
        """Cuenta tokens usando el tokenizador configurado o fallback chars/4.

        Args:
            text: Texto a contar.

        Returns:
            Numero de tokens (minimo 1).
        """
        if self._use_real_tokenizer:
            return self._token_estimator.count(text)
        return max(1, len(text) // int(CHARS_PER_TOKEN))

    def _window_total_tokens(self, window: ContextWindow) -> int:
        """Calcula tokens totales de una ventana.

        Args:
            window: Ventana de contexto.

        Returns:
            Suma de tokens de todas las secciones.
        """
        return sum(
            self._count_tokens(s.content)
            for s in window.sections.values()
        )

    def _window_over_budget(self, window: ContextWindow) -> bool:
        """Verifica si la ventana excede el presupuesto.

        Args:
            window: Ventana de contexto.

        Returns:
            True si supera el presupuesto.
        """
        return self._window_total_tokens(window) > window.total_budget

    def _inject_estimator(self, window: ContextWindow) -> None:
        """Inyecta el token estimator en todas las secciones de la ventana.

        Args:
            window: Ventana de contexto.
        """
        if not self._use_real_tokenizer:
            return
        for section in window.sections.values():
            section._token_estimator = self._token_estimator

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def create_window(self) -> ContextWindow:
        """Create a new context window with the global budget.

        Returns:
            Nueva ContextWindow.
        """
        return ContextWindow(total_budget=self._total_budget)

    def optimize(self, window: ContextWindow) -> ContextWindow:
        """Optimize a context window to fit within budget.

        Strategies applied in order:
          1. Truncate over-budget sections (lowest priority first)
          2. Summarize conversation history if still over budget
          3. Compress tool outputs (observation masking + fallback truncation)
          4. Drop lowest-priority sections if still over budget
          5. Last resort: hard truncate at token limit

        Args:
            window: The context window to optimize.

        Returns:
            Optimized window (same object, modified in place).
        """
        self._inject_estimator(window)

        before = self._window_total_tokens(window)
        self._stats["optimizations"] += 1
        self._stats["tokens_before"] += before

        if not self._window_over_budget(window):
            self._stats["tokens_after"] += before
            return window

        # Strategy 1: Truncate over-budget sections (lowest priority first)
        over_budget_sections = sorted(
            [s for s in window.sections.values()
             if self._count_tokens(s.content) > s.max_tokens and not s.frozen],
            key=lambda x: x.priority,
            reverse=True,
        )
        for section in over_budget_sections:
            if not self._window_over_budget(window):
                break
            if section.truncate_to_budget():
                self._stats["truncations"] += 1
                logger.debug("Truncated section '%s' to budget", section.name)

        # Strategy 2: Summarize conversation history
        conv_section = window.get_section("conversation_history")
        if conv_section and self._window_over_budget(window) and not conv_section.frozen and summarize_conversation(self, conv_section):
            self._stats["summarizations"] += 1

        # Strategy 3: Compress tool outputs
        tool_section = window.get_section("tool_outputs")
        if tool_section and self._window_over_budget(window) and not tool_section.frozen:
            compress_tool_outputs(self, tool_section)

        # Strategy 4: Drop lowest-priority non-frozen sections
        if self._window_over_budget(window):
            droppable = sorted(
                [
                    (name, s) for name, s in window.sections.items()
                    if not s.frozen and s.priority >= PRIORITY_LOW
                ],
                key=lambda x: x[1].priority,
                reverse=True,
            )
            for name, section in droppable:
                if not self._window_over_budget(window):
                    break
                if section.content:
                    if self._count_tokens(section.content) > 50:
                        section.content = aggressive_compress(section.content)
                        logger.debug("Compressed section '%s' aggressively", name)
                    else:
                        window.remove_section(name)
                        self._stats["sections_dropped"] += 1
                        logger.debug("Dropped section '%s'", name)

        # Strategy 5: Hard truncate (last resort)
        if self._window_over_budget(window):
            window = hard_truncate(self, window)

        after = self._window_total_tokens(window)
        self._stats["tokens_after"] += after
        self._stats["tokens_saved"] += (before - after)

        pct = compression_pct(before, after)
        logger.debug(
            "ContextWindow optimized: %d -> %d tokens (%.1f%% compression)",
            before, after, pct,
        )

        return window

    def compact_history(
        self,
        history: list[dict[str, Any]],
        max_messages: int = 8,
    ) -> list[dict[str, Any]]:
        """Compacta historial de conversacion usando sliding window + summary.

        Args:
            history: Lista de mensajes con 'role' y 'content'.
            max_messages: Maximo de mensajes a mantener completos.

        Returns:
            Lista compactada de mensajes.
        """
        if not history or len(history) <= max_messages:
            return history

        keep = history[-self._sliding_window_size:]
        compress = history[:-self._sliding_window_size]

        summary_text = summarize_messages(compress)

        compacted: list[dict] = [
            {
                "role": "system",
                "content": f"[COMPACTED] {summary_text}",
                "compressed": True,
                "original_messages": len(compress),
            }
        ]
        compacted.extend(keep)

        logger.debug(
            "History compaction: %d -> %d messages",
            len(history), len(compacted),
        )
        return compacted

    # ------------------------------------------------------------------
    # Forwarding methods para compatibilidad (delegan a context_compression)
    # ------------------------------------------------------------------

    def _summarize_conversation(self, section: ContextSection) -> bool:
        """Summarize conversation history (delega a context_compression).

        Args:
            section: Seccion de historial de conversacion.

        Returns:
            True si se comprimio algo.
        """
        from harness.memory_rag.context_compression import summarize_conversation as _sc
        return _sc(self, section)

    def _compress_tool_outputs(self, section: ContextSection) -> bool:
        """Comprime tool outputs (delega a context_compression).

        Args:
            section: Seccion de tool outputs.

        Returns:
            True si se comprimio algo.
        """
        from harness.memory_rag.context_compression import compress_tool_outputs as _cto
        return _cto(self, section)

    def _hard_truncate(self, window: ContextWindow) -> ContextWindow:
        """Hard truncate at token limit (delega a context_compression).

        Args:
            window: Ventana de contexto a truncar.

        Returns:
            Ventana truncada.
        """
        from harness.memory_rag.context_compression import hard_truncate as _ht
        return _ht(self, window)

    @staticmethod
    def _aggressive_compress(text: str) -> str:
        """Compress text aggressively (delega a context_compression).

        Args:
            text: Texto a comprimir.

        Returns:
            Texto comprimido.
        """
        from harness.memory_rag.context_compression import aggressive_compress as _ac
        return _ac(text)

    @staticmethod
    def _apply_observation_masking(text: str, max_tokens: int = 500) -> str:
        """Observation Masking (delega a context_compression).

        Args:
            text: Texto a procesar.
            max_tokens: Umbral de tokens para aplicar masking.

        Returns:
            Texto con masking aplicado.
        """
        from harness.memory_rag.context_compression import (
            _apply_observation_masking as _om,
        )
        return _om(text, max_tokens)

    @staticmethod
    def _default_summary(text: str) -> str:
        """Default summarization (delega a context_compression).

        Args:
            text: Texto a resumir.

        Returns:
            Resumen del texto.
        """
        from harness.memory_rag.context_compression import _default_summary_fn as _ds
        return _ds(text)

    def _summarize_messages(self, messages: list[dict[str, Any]]) -> str:
        """Summarize messages (delega a context_compression).

        Args:
            messages: Lista de mensajes.

        Returns:
            Resumen textual.
        """
        from harness.memory_rag.context_compression import summarize_messages as _sm
        return _sm(messages)

    def _section_over_budget(self, section: ContextSection) -> bool:
        """Verifica si una seccion excede su presupuesto de tokens (delega a context_compression).

        Args:
            section: ContextSection a verificar.

        Returns:
            True si supera su max_tokens.
        """
        from harness.memory_rag.context_compression import _section_over_budget as _sob
        return _sob(self, section)

    # get_stats() heredado de StatsMixin
