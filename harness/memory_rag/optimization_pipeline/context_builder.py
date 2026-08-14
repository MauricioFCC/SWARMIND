"""Mixin de construccion de contexto para ``OptimizationPipeline``.

Extraido mecanicamente de ``optimization_pipeline.py`` (regla AGR < 500
lineas). Contiene los helpers internos de construccion de la ventana de
contexto, extraccion de secciones, formateo de historial, cache key y
actualizacion de estadisticas.
"""
from __future__ import annotations

from typing import Any

from ..context_window_manager import ContextWindow
from .models import OptimizationResult


class _ContextBuilderMixin:
    """Helpers internos de construccion de contexto y estadisticas."""

    def _build_context_window(
        self,
        agent_id: str,
        system_parts: dict[str, str],
        user_message: str,
        rag_context: str,
        conversation_history: list[dict[str, Any]] | None,
        tool_outputs: str,
        domains: list[str],
    ) -> ContextWindow:
        """Build initial context window from all parts."""
        window = ContextWindow()

        # System sections (critical, frozen)
        for section_name, content in system_parts.items():
            window.add_section(
                name=section_name,
                content=content,
                frozen=True,
            )

        # Skill context (if lazy loader enabled)
        if self._skill_loader:
            skill_context = self._skill_loader.get_active_skills_context()
            if skill_context:
                window.add_section(
                    name="skill_context",
                    content=skill_context,
                    max_tokens=2000,
                )

            # Tier 1 catalog (always included, compact)
            tier1 = self._skill_loader.get_tier1_prompt(domain_filter=domains)
            window.add_section(
                name="skill_catalog",
                content=tier1,
                frozen=True,
                max_tokens=500,
            )

        # RAG context
        if rag_context:
            window.add_section(
                name="rag_context",
                content=rag_context,
                max_tokens=2000,
            )

        # Conversation history
        if conversation_history:
            # First compress trajectory
            if self._trajectory_compressor:
                conversation_history = self._trajectory_compressor.compress(
                    conversation_history
                )

            history_text = self._format_history(conversation_history)
            window.add_section(
                name="conversation_history",
                content=history_text,
                max_tokens=3000,
            )

        # Tool outputs
        if tool_outputs:
            window.add_section(
                name="tool_outputs",
                content=tool_outputs,
                max_tokens=2000,
            )

        return window

    def _extract_sections(self, window: ContextWindow) -> dict[str, str]:
        """Extract sections from context window for prompt cache builder."""
        sections = {}
        for name, section in window.sections.items():
            sections[name] = section.content
        return sections

    @staticmethod
    def _format_history(history: list[dict[str, Any]]) -> str:
        """Format conversation history as text."""
        parts = []
        for msg in history:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                parts.append(f"[{role}]: {content}")
        return "\n".join(parts)

    @staticmethod
    def _build_cache_key(
        agent_id: str,
        system_parts: dict[str, str] | None,
        user_message: str,
        domains: list[str],
    ) -> str:
        """Build a deterministic cache key from non-user parts."""
        parts = [f"agent:{agent_id}", f"domains:{','.join(domains)}"]
        if system_parts:
            for key, value in system_parts.items():
                parts.append(f"{key}:{value[:200]}")
        if user_message:
            parts.append(f"msg:{user_message}")
        return "|".join(parts)

    def _update_stats(self, result: OptimizationResult) -> None:
        """Update global stats."""
        self._stats["optimizations"] += 1
        self._stats["tokens_before"] += result.tokens_before
        self._stats["tokens_after"] += result.tokens_after
        self._stats["tokens_saved"] += result.tokens_saved
        self._stats["total_duration_ms"] += result.duration_ms
