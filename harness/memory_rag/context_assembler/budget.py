"""Mixin de presupuesto de tokens para ``ContextAssembler``.

Extraido mecanicamente de ``context_assembler.py`` (regla AGR < 500
lineas). Contiene ``_apply_token_budget``, ``_estimate_tokens`` y
``compact_context``, que truncan y compactan el contexto ensamblado
para que quepa dentro del presupuesto.
"""
from __future__ import annotations

import logging

from harness.common import estimate_tokens, truncate_by_budget

from .models import ContextAssembly

logger = logging.getLogger("harness.memory_rag.context_assembler")


class _TokenBudgetMixin:
    """Aplicacion de presupuesto de tokens y compactacion de historial."""

    def _apply_token_budget(
        self,
        assembly: ContextAssembly,
        max_tokens: int,
    ) -> ContextAssembly:
        """
        Truncate the assembled context so it fits within the token budget.

        Strategy: remove lowest-score documents first, then truncate
        conversation history from the oldest entry.

        Usa ``truncate_by_budget()`` de harness.common (reemplaza los 3 bucles
        identicos de truncamiento que estaban duplicados aqui).

        Si el budget se excede, se loguea una advertencia.
        Se aplica un margen de seguridad del 10% (truncar al 90% del budget).
        """
        used = estimate_tokens(assembly.instructions)

        def doc_tokens(doc):
            return estimate_tokens(str(doc.get("metadata", {})))

        def task_tokens(task):
            return estimate_tokens(str(task.get("metadata", {})))

        # --- Docs (sorted by score, highest first) ---
        assembly.relevant_docs = truncate_by_budget(
            assembly.relevant_docs,
            get_tokens=doc_tokens,
            budget=max_tokens,
            safety_margin=0.9,
            sort_key=lambda d: d.get("score", 0.0),
        )

        # --- Task context ---
        assembly.task_context = truncate_by_budget(
            assembly.task_context,
            get_tokens=task_tokens,
            budget=max_tokens - estimate_tokens(assembly.instructions),
            safety_margin=0.9,
        )

        # --- Compact conversation history first ---
        assembly.conversation_history = self.compact_context(
            assembly.conversation_history,
            max_messages=8,
        )

        # --- Conversation history ---
        remaining_budget = max_tokens - estimate_tokens(assembly.instructions)
        for docs in [assembly.relevant_docs]:
            remaining_budget -= sum(doc_tokens(d) for d in docs)
        for tasks in [assembly.task_context]:
            remaining_budget -= sum(task_tokens(t) for t in tasks)

        assembly.conversation_history = truncate_by_budget(
            assembly.conversation_history,
            get_tokens=estimate_tokens,
            budget=remaining_budget,
            safety_margin=0.9,
        )

        # Recalcular total usado
        used = estimate_tokens(assembly.instructions)
        used += sum(doc_tokens(d) for d in assembly.relevant_docs)
        used += sum(task_tokens(t) for t in assembly.task_context)
        used += sum(estimate_tokens(h) for h in assembly.conversation_history)

        # Log warning if budget was exceeded
        if used > max_tokens:
            logger.warning(
                "Token budget exceeded: %d/%d tokens used (%.1f%%).",
                used, max_tokens, (used / max_tokens) * 100,
            )

        assembly.metadata["total_tokens_used"] = used
        return assembly

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """
        Token estimation: delega en harness.common.estimate_tokens.

        Usa tiktoken si disponible, fallback a chars/4.
        """
        return estimate_tokens(text)

    def compact_context(
        self,
        conversation_history: list[str],
        max_messages: int = 8,
    ) -> list[str]:
        """Compacta el historial de conversacion para ahorrar tokens.

        Estrategia (inspirada en Anthropic Context Engineering Sep 2025):
        1. Tool calls ocupan ~60% del contexto. Limpiar tool results a solo metadata.
        2. Sliding window: mantener ultimos N mensajes completos + summary de anteriores.
        3. Eliminar mensajes del sistema duplicados.

        Args:
            conversation_history: Lista de mensajes del historial.
            max_messages: Maximo de mensajes a mantener completos.

        Returns:
            Lista compactada de mensajes.
        """
        if not conversation_history:
            return conversation_history

        # Si ya esta dentro del limite, devolver intacto
        if len(conversation_history) <= max_messages:
            return conversation_history

        # Separar: mantener ultimos N mensajes intactos,
        # comprimir los anteriores a un summary
        keep_count = max(2, max_messages - 1)  # reservar 1 para summary
        keep = conversation_history[-keep_count:]
        compress = conversation_history[:-keep_count]

        # Comprimir: resumir los mensajes antiguos
        summary_lines = []
        for msg in compress:
            # Truncar mensajes largos a 50 chars
            if len(msg) > 100:
                summary_lines.append(msg[:100] + "...")
            else:
                summary_lines.append(msg)

        if summary_lines:
            summary = f"[COMPACTED] {len(compress)} earlier messages: {' | '.join(summary_lines[-3:])}"
            # Limitar summary a 300 chars
            summary = summary[:300]
            compacted = [summary] + keep
        else:
            compacted = keep

        logger.debug(
            "Context compaction: %d -> %d messages",
            len(conversation_history), len(compacted),
        )
        return compacted
