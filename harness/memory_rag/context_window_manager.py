"""
Context Window Manager — Gestion adaptativa de la ventana de contexto.

Basado en estrategias 2026 de context window management:
  - Priority ordering: system prompt > current instruction > recent history > RAG
  - Sliding window con summarization de turnos antiguos
  - Truncation con budget allocation por seccion
  - Session-aware compaction (mantener solo lo esencial)

Ahorro estimado: 40-60% de tokens en historial de conversacion.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Prioridades de secciones (mas bajo = se trunca primero)
PRIORITY_CRITICAL = 0     # Nunca se trunca
PRIORITY_HIGH = 1         # Solo se trunca si es absolutamente necesario
PRIORITY_NORMAL = 2       # Se trunca normalmente
PRIORITY_LOW = 3          # Se trunca primero
PRIORITY_BACKGROUND = 4   # Se elimina primero

SECTION_PRIORITIES: Dict[str, int] = {
    "system_identity": PRIORITY_CRITICAL,
    "system_rules": PRIORITY_CRITICAL,
    "system_guardrails": PRIORITY_CRITICAL,
    "current_instruction": PRIORITY_HIGH,
    "session_context": PRIORITY_HIGH,
    "skill_context": PRIORITY_NORMAL,
    "rag_context": PRIORITY_LOW,
    "conversation_history": PRIORITY_LOW,
    "tool_outputs": PRIORITY_BACKGROUND,
}

# Tamaños maximos por defecto (en tokens aproximados)
DEFAULT_BUDGETS: Dict[str, int] = {
    "system_identity": 500,
    "system_rules": 1000,
    "system_guardrails": 500,
    "current_instruction": 400,
    "session_context": 800,
    "skill_context": 2000,
    "rag_context": 2000,
    "conversation_history": 3000,
    "tool_outputs": 2000,
}

# Estimacion: ~4 chars por token
CHARS_PER_TOKEN = 4.0

# Resumen de conversacion: chars max
MAX_SUMMARY_CHARS = 500

# Sliding window: mantener ultimos N mensajes completos
SLIDING_WINDOW_SIZE = 6


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------

@dataclass
class ContextSection:
    """A section of the context window."""
    name: str
    content: str
    priority: int = PRIORITY_NORMAL
    max_tokens: int = 1000
    frozen: bool = False  # True = no comprimir/truncar
    compressed: bool = False

    @property
    def token_estimate(self) -> int:
        return max(1, len(self.content) // int(CHARS_PER_TOKEN))

    @property
    def over_budget(self) -> bool:
        return self.token_estimate > self.max_tokens

    def truncate_to_budget(self) -> bool:
        """Truncar contenido al budget. Returns True if truncated."""
        if self.frozen or not self.over_budget:
            return False
        max_chars = int(self.max_tokens * CHARS_PER_TOKEN)
        if len(self.content) > max_chars:
            # Truncar inteligentemente al inicio del ultimo parrafo
            truncated = self.content[:max_chars]
            last_para = truncated.rfind("\n\n")
            if last_para > max_chars // 2:
                truncated = truncated[:last_para]
            self.content = truncated + "\n\n[...truncated...]"
            self.compressed = True
            return True
        return False


# ---------------------------------------------------------------------------
# Context Window
# ---------------------------------------------------------------------------

@dataclass
class ContextWindow:
    """The full context window for a single LLM call."""
    sections: Dict[str, ContextSection] = field(default_factory=dict)
    total_budget: int = 12000  # tokens totales (default)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_section(
        self,
        name: str,
        content: str,
        priority: Optional[int] = None,
        max_tokens: Optional[int] = None,
        frozen: bool = False,
    ) -> ContextSection:
        """Add or update a section."""
        section = ContextSection(
            name=name,
            content=content,
            priority=priority or SECTION_PRIORITIES.get(name, PRIORITY_NORMAL),
            max_tokens=max_tokens or DEFAULT_BUDGETS.get(name, 1000),
            frozen=frozen,
        )
        self.sections[name] = section
        return section

    def get_section(self, name: str) -> Optional[ContextSection]:
        return self.sections.get(name)

    def remove_section(self, name: str) -> bool:
        return self.sections.pop(name, None) is not None

    @property
    def total_tokens(self) -> int:
        return sum(s.token_estimate for s in self.sections.values())

    @property
    def over_budget(self) -> bool:
        return self.total_tokens > self.total_budget

    def to_prompt(self, format: str = "compact") -> str:
        """
        Render sections as a formatted prompt string.

        Args:
            format: 'compact' = single block, 'labeled' = with headers.

        Returns:
            Formatted prompt string.
        """
        if format == "labeled":
            parts = []
            # Critical first (in priority order)
            for name, section in sorted(
                self.sections.items(),
                key=lambda x: x[1].priority,
            ):
                if section.content:
                    header = name.replace("_", " ").title()
                    parts.append(f"=== {header} ===\n{section.content}")
            return "\n\n".join(parts)
        else:
            # Compact: just concatenate in priority order
            sections_in_order = sorted(
                self.sections.items(),
                key=lambda x: x[1].priority,
            )
            return "\n".join(s.content for _, s in sections_in_order if s.content)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_budget": self.total_budget,
            "total_tokens": self.total_tokens,
            "over_budget": self.over_budget,
            "sections": {
                k: {
                    "name": v.name,
                    "tokens": v.token_estimate,
                    "priority": v.priority,
                    "max_tokens": v.max_tokens,
                    "frozen": v.frozen,
                    "compressed": v.compressed,
                    "over_budget": v.over_budget,
                }
                for k, v in self.sections.items()
            },
        }


# ---------------------------------------------------------------------------
# Context Window Manager
# ---------------------------------------------------------------------------

class ContextWindowManager:
    """
    Gestiona la ventana de contexto para llamadas LLM.

    Estrategias:
      1. Priority ordering: secciones criticas primero, fondo despues
      2. Budget allocation: cada seccion tiene un maximo de tokens
      3. Sliding window: mantener ultimos N mensajes completos
      4. Summarization: comprimir historial antiguo a resumen
      5. Section dropping: eliminar secciones de baja prioridad si es necesario

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
        summary_fn: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._total_budget = total_budget
        self._sliding_window_size = sliding_window_size
        self._summary_fn = summary_fn or self._default_summary
        self._stats: Dict[str, Any] = {
            "optimizations": 0,
            "truncations": 0,
            "summarizations": 0,
            "sections_dropped": 0,
            "tokens_before": 0,
            "tokens_after": 0,
            "tokens_saved": 0,
        }

        logger.info(
            "ContextWindowManager initialized (budget=%d, sliding=%d)",
            total_budget, sliding_window_size,
        )

    def create_window(self) -> ContextWindow:
        """Create a new context window with the global budget."""
        return ContextWindow(total_budget=self._total_budget)

    def optimize(self, window: ContextWindow) -> ContextWindow:
        """
        Optimize a context window to fit within budget.

        Strategies applied in order:
          1. Truncate over-budget sections (lowest priority first)
          2. Summarize conversation history if still over budget
          3. Drop lowest-priority sections if still over budget
          4. Last resort: hard truncate at token limit

        Args:
            window: The context window to optimize.

        Returns:
            Optimized window (same object, modified in place).
        """
        before = window.total_tokens
        self._stats["optimizations"] += 1
        self._stats["tokens_before"] += before

        if not window.over_budget:
            self._stats["tokens_after"] += before
            return window

        # Strategy 1: Truncate over-budget sections (lowest priority first)
        over_budget_sections = sorted(
            [s for s in window.sections.values() if s.over_budget and not s.frozen],
            key=lambda x: x.priority,
            reverse=True,  # Start with lowest priority
        )
        for section in over_budget_sections:
            if not window.over_budget:
                break
            if section.truncate_to_budget():
                self._stats["truncations"] += 1
                logger.debug("Truncated section '%s' to budget", section.name)

        # Strategy 2: Summarize conversation history
        conv_section = window.get_section("conversation_history")
        if conv_section and window.over_budget and not conv_section.frozen:
            if self._summarize_conversation(conv_section):
                self._stats["summarizations"] += 1

        # Strategy 3: Compress tool outputs
        tool_section = window.get_section("tool_outputs")
        if tool_section and window.over_budget and not tool_section.frozen:
            self._compress_tool_outputs(tool_section)

        # Strategy 4: Drop lowest-priority non-frozen sections
        if window.over_budget:
            droppable = sorted(
                [
                    (name, s) for name, s in window.sections.items()
                    if not s.frozen and s.priority >= PRIORITY_LOW
                ],
                key=lambda x: x[1].priority,
                reverse=True,
            )
            for name, section in droppable:
                if not window.over_budget:
                    break
                if section.content:
                    # Try compressing first
                    if len(section.content) > 200:
                        section.content = self._aggressive_compress(section.content)
                        logger.debug("Compressed section '%s' aggressively", name)
                    else:
                        window.remove_section(name)
                        self._stats["sections_dropped"] += 1
                        logger.debug("Dropped section '%s'", name)

        # Strategy 5: Hard truncate (last resort)
        if window.over_budget:
            window = self._hard_truncate(window)

        after = window.total_tokens
        self._stats["tokens_after"] += after
        self._stats["tokens_saved"] += (before - after)

        compression_pct = (1 - after / max(before, 1)) * 100
        logger.debug(
            "ContextWindow optimized: %d -> %d tokens (%.1f%% compression)",
            before, after, compression_pct,
        )

        return window

    def compact_history(
        self,
        history: List[Dict[str, Any]],
        max_messages: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Compacta historial de conversacion usando sliding window + summary.

        Args:
            history: Lista de mensajes con 'role' y 'content'.
            max_messages: Maximo de mensajes a mantener completos.

        Returns:
            Lista compactada de mensajes.
        """
        if not history or len(history) <= max_messages:
            return history

        # Sliding window: mantener ultimos N mensajes completos
        keep = history[-self._sliding_window_size:]
        compress = history[:-self._sliding_window_size]

        # Summarize compressed portion
        summary_text = self._summarize_messages(compress)

        # Insert summary as first message
        compacted: List[Dict] = [
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

    def get_stats(self) -> Dict[str, Any]:
        """Return manager statistics."""
        stats = dict(self._stats)
        total_before = stats.get("tokens_before", 1)
        if total_before > 0:
            stats["avg_compression_pct"] = round(
                stats["tokens_saved"] / total_before * 100, 1
            )
        else:
            stats["avg_compression_pct"] = 0.0
        return stats

    # ------------------------------------------------------------------
    # Internal optimization strategies
    # ------------------------------------------------------------------

    def _summarize_conversation(self, section: ContextSection) -> bool:
        """Summarize conversation history to fit within budget."""
        if not section.content:
            return False

        max_chars = int(section.max_tokens * CHARS_PER_TOKEN)
        if len(section.content) <= max_chars:
            return False

        # Split into messages
        messages = section.content.split("\n\n")
        if len(messages) <= 3:
            # Too few messages, just truncate
            section.truncate_to_budget()
            return True

        # Keep last N messages, summarize rest
        keep_count = min(self._sliding_window_size, len(messages) - 1)
        keep = messages[-keep_count:]
        summarize = messages[:-keep_count]

        summary = self._summary_fn("\n".join(summarize))
        section.content = (
            f"[COMPACTED - {len(summarize)} previous messages]\n"
            f"{summary}\n\n"
            + "\n\n".join(keep)
        )
        section.compressed = True

        # If still over budget, truncate
        if section.over_budget:
            section.truncate_to_budget()

        return True

    def _compress_tool_outputs(self, section: ContextSection) -> bool:
        """Compress tool outputs by keeping only key metadata."""
        if not section.content:
            return False

        # Replace tool results with compact summaries
        lines = section.content.split("\n")
        compressed: List[str] = []
        in_tool_result = False
        tool_result_lines = 0

        for line in lines:
            if line.startswith("Tool:") or line.startswith(">"):
                in_tool_result = True
                tool_result_lines = 0
                compressed.append(line)
                continue

            if in_tool_result:
                tool_result_lines += 1
                if tool_result_lines <= 3:
                    compressed.append(line)
                elif tool_result_lines == 4:
                    compressed.append("  ... (result truncated)")
                continue

            compressed.append(line)

        section.content = "\n".join(compressed)
        section.compressed = True
        return True

    def _hard_truncate(self, window: ContextWindow) -> ContextWindow:
        """
        Last resort: hard truncate at token limit.
        Removes content from lowest priority sections first.
        """
        max_chars = int(window.total_budget * CHARS_PER_TOKEN * 0.95)

        # Build ordered list of sections by priority (lowest first)
        ordered = sorted(
            window.sections.items(),
            key=lambda x: (x[1].priority, x[1].max_tokens),
            reverse=True,
        )

        current_chars = sum(len(s.content) for _, s in window.sections.items())

        for name, section in ordered:
            if current_chars <= max_chars:
                break
            if section.frozen:
                continue

            # Remove or heavily truncate
            section_chars = len(section.content)
            if section.priority >= PRIORITY_LOW and section_chars > 100:
                # Remove section entirely if low priority
                window.remove_section(name)
                current_chars -= section_chars
                logger.debug("Hard truncate: removed section '%s'", name)
            elif section_chars > 200:
                # Heavy truncation
                keep_chars = min(200, int(section.max_tokens * CHARS_PER_TOKEN * 0.5))
                section.content = section.content[:keep_chars] + "\n[...]"
                section.compressed = True
                current_chars = current_chars - section_chars + len(section.content)
                logger.debug("Hard truncate: compressed section '%s'", name)

        return window

    @staticmethod
    def _aggressive_compress(text: str) -> str:
        """Compress text aggressively by removing redundant whitespace/lines."""
        # Remove empty lines
        lines = [l for l in text.split("\n") if l.strip()]
        # Remove markdown formatting
        text = "\n".join(lines)
        # Collapse multiple spaces
        text = re.sub(r" {2,}", " ", text)
        return text[:1000]  # Hard limit

    @staticmethod
    def _default_summary(text: str) -> str:
        """Default summarization: extract first 500 chars."""
        text = text.strip()
        if len(text) <= MAX_SUMMARY_CHARS:
            return text
        # Try to extract first meaningful lines
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        summary_lines: List[str] = []
        char_count = 0
        for line in lines:
            char_count += len(line) + 1
            if char_count > MAX_SUMMARY_CHARS:
                break
            summary_lines.append(line)
        return " | ".join(summary_lines) if summary_lines else text[:MAX_SUMMARY_CHARS]

    def _summarize_messages(self, messages: List[Dict[str, Any]]) -> str:
        """Summarize a list of messages."""
        # Extract key information from each message
        key_points: List[str] = []
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            # Truncate long content
            if isinstance(content, str) and content:
                if len(content) > 150:
                    content = content[:150] + "..."
                key_points.append(f"[{role}] {content}")
        return " | ".join(key_points) if key_points else "(history compressed)"
