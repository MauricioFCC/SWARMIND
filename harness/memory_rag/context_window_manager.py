"""
Context Window Manager — Gestion adaptativa de la ventana de contexto.

Basado en estrategias 2026 de context window management:
  - Priority ordering: system prompt > current instruction > recent history > RAG
  - Sliding window con summarization de turnos antiguos
  - Truncation con budget allocation por seccion
  - Session-aware compaction (mantener solo lo esencial)
  - TokenEstimator con soporte multi-modelo (tiktoken + LRU cache)
  - Observation Masking: reemplaza tool outputs grandes con placeholders

Estrategias de compresion extraidas a context_compression.py.

Ahorro estimado: 40-60% de tokens en historial de conversacion.
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from harness.common import CHARS_PER_TOKEN, StatsMixin, compression_pct
from harness.memory_rag.context_compression import (
    aggressive_compress,
    compress_tool_outputs,
    hard_truncate,
    summarize_conversation,
    summarize_messages,
)

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

MAX_SUMMARY_CHARS = 500
SLIDING_WINDOW_SIZE = 6


# ---------------------------------------------------------------------------
# TokenEstimator
# ---------------------------------------------------------------------------

class TokenEstimator:
    """Estimador de tokens con tokenizador real y cache LRU.

    Soporta multiples familias de modelo y degradacion graceful
    si ``tiktoken`` no esta instalado.

    Uso:
        te = TokenEstimator(model_family="claude")
        tokens = te.count("texto a contar")
        truncado = te.truncate_to_token_limit("texto largo", max_tokens=100)
    """

    _ENCODING_MAP: Dict[str, str] = {
        "claude": "cl100k_base",
        "gpt-4": "gpt-4",
        "gemini": "cl100k_base",
        "llama": "cl100k_base",
    }

    def __init__(self, model_family: str = "claude") -> None:
        """Inicializa el estimador de tokens.

        Args:
            model_family: Familia de modelo ("claude", "gpt-4", "gemini", "llama").
        """
        self.model_family = model_family
        self._cache: OrderedDict[str, int] = OrderedDict()
        self._cache_maxsize = 2048
        self._encoder = self._init_encoder()
        self._warned: bool = False

    def _init_encoder(self) -> Any:
        """Inicializa el encoder tiktoken segun model_family.

        Returns:
            Encoder tiktoken, o None si no esta disponible.
        """
        try:
            import tiktoken  # type: ignore
            if self.model_family == "gpt-4":
                return tiktoken.encoding_for_model("gpt-4")
            encoding_name = self._ENCODING_MAP.get(
                self.model_family, "cl100k_base"
            )
            return tiktoken.get_encoding(encoding_name)
        except ImportError:
            logger.warning(
                "TokenEstimator: tiktoken no instalado, "
                "usando chars/4 como fallback"
            )
            return None
        except Exception as e:
            logger.warning(
                "TokenEstimator: error inicializando encoder (%s), "
                "usando chars/4 como fallback", e
            )
            return None

    def count(self, text: str) -> int:
        """Cuenta tokens reales usando el tokenizador configurado.

        Resultados cacheados con LRU (max 2048 entradas).

        Args:
            text: Texto a contar.

        Returns:
            Numero estimado de tokens (minimo 1).
        """
        if not text:
            return 1

        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]

        if self._encoder is not None:
            try:
                count = len(self._encoder.encode(text))
            except Exception:
                count = max(1, len(text) // 4)
        else:
            count = max(1, len(text) // 4)

        self._cache[text] = count
        if len(self._cache) > self._cache_maxsize:
            self._cache.popitem(last=False)

        return count

    def truncate_to_token_limit(self, text: str, max_tokens: int) -> str:
        """Trunca texto para que no exceda max_tokens.

        Args:
            text: Texto a truncar.
            max_tokens: Maximo de tokens permitidos (min 1).

        Returns:
            Texto truncado que cumple con el limite.
        """
        if not text or max_tokens < 1:
            return ""

        if self.count(text) <= max_tokens:
            return text

        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.count(text[:mid]) <= max_tokens:
                lo = mid
            else:
                hi = mid - 1

        return text[:lo]


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
    frozen: bool = False
    compressed: bool = False
    _token_estimator: Optional[TokenEstimator] = field(
        default=None, repr=False, compare=False
    )

    @property
    def token_estimate(self) -> int:
        """Estima tokens usando el tokenizador real si esta disponible."""
        if self._token_estimator is not None:
            return self._token_estimator.count(self.content)
        return max(1, len(self.content) // int(CHARS_PER_TOKEN))

    @property
    def over_budget(self) -> bool:
        """Indica si la seccion excede su presupuesto de tokens."""
        return self.token_estimate > self.max_tokens

    def truncate_to_budget(self) -> bool:
        """Trunca contenido al presupuesto.

        Returns:
            True si se trunco algo.
        """
        if self.frozen or not self.over_budget:
            return False

        if self._token_estimator is not None:
            current_len = len(self.content)
            truncated = self._token_estimator.truncate_to_token_limit(
                self.content, self.max_tokens
            )
            margin = int(current_len * 0.1)
            last_para = truncated.rfind("\n\n")
            if last_para > len(truncated) - margin:
                truncated = truncated[:last_para]
            self.content = truncated + "\n\n[...truncated...]"
        else:
            max_chars = int(self.max_tokens * CHARS_PER_TOKEN)
            if len(self.content) > max_chars:
                truncated = self.content[:max_chars]
                last_para = truncated.rfind("\n\n")
                if last_para > max_chars // 2:
                    truncated = truncated[:last_para]
                self.content = truncated + "\n\n[...truncated...]"

        self.compressed = True
        return True


# ---------------------------------------------------------------------------
# Context Window
# ---------------------------------------------------------------------------

@dataclass
class ContextWindow:
    """The full context window for a single LLM call."""
    sections: Dict[str, ContextSection] = field(default_factory=dict)
    total_budget: int = 12000
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
        """Obtiene una seccion por nombre."""
        return self.sections.get(name)

    def remove_section(self, name: str) -> bool:
        """Elimina una seccion por nombre."""
        return self.sections.pop(name, None) is not None

    @property
    def total_tokens(self) -> int:
        """Total de tokens en todas las secciones."""
        return sum(s.token_estimate for s in self.sections.values())

    @property
    def over_budget(self) -> bool:
        """Indica si la ventana excede el presupuesto."""
        return self.total_tokens > self.total_budget

    def to_prompt(self, format: str = "compact") -> str:
        """Render sections as a formatted prompt string.

        Args:
            format: 'compact' = single block, 'labeled' = with headers.

        Returns:
            Formatted prompt string.
        """
        if format == "labeled":
            parts = []
            for name, section in sorted(
                self.sections.items(),
                key=lambda x: x[1].priority,
            ):
                if section.content:
                    header = name.replace("_", " ").title()
                    parts.append(f"=== {header} ===\n{section.content}")
            return "\n\n".join(parts)
        else:
            sections_in_order = sorted(
                self.sections.items(),
                key=lambda x: x[1].priority,
            )
            return "\n".join(s.content for _, s in sections_in_order if s.content)

    def to_dict(self) -> Dict[str, Any]:
        """Serializa la ventana a diccionario (sin contenido completo)."""
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
        summary_fn: Optional[Callable[[str], str]] = None,
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
        if conv_section and self._window_over_budget(window) and not conv_section.frozen:
            if summarize_conversation(self, conv_section):
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
        history: List[Dict[str, Any]],
        max_messages: int = 8,
    ) -> List[Dict[str, Any]]:
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
        from harness.memory_rag.context_compression import _apply_observation_masking as _om
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

    def _summarize_messages(self, messages: List[Dict[str, Any]]) -> str:
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
