"""
Context Window Manager — Gestion adaptativa de la ventana de contexto.

Basado en estrategias 2026 de context window management:
  - Priority ordering: system prompt > current instruction > recent history > RAG
  - Sliding window con summarization de turnos antiguos
  - Truncation con budget allocation por seccion
  - Session-aware compaction (mantener solo lo esencial)
  - TokenEstimator con soporte multi-modelo (tiktoken + LRU cache)
  - Observation Masking: reemplaza tool outputs grandes con placeholders

Ahorro estimado: 40-60% de tokens en historial de conversacion.
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from harness.common import CHARS_PER_TOKEN, StatsMixin, compression_pct, estimate_tokens

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

# Resumen de conversacion: chars max
MAX_SUMMARY_CHARS = 500

# Sliding window: mantener ultimos N mensajes completos
SLIDING_WINDOW_SIZE = 6


# ---------------------------------------------------------------------------
# TokenEstimator — Tokenizador real con soporte multi-modelo + LRU cache
# ---------------------------------------------------------------------------

class TokenEstimator:
    """
    Estimador de tokens con tokenizador real y cache LRU.

    Soporta múltiples familias de modelo y degradación graceful
    si ``tiktoken`` no está instalado.

    Uso:
        te = TokenEstimator(model_family="claude")
        tokens = te.count("texto a contar")
        truncado = te.truncate_to_token_limit("texto largo", max_tokens=100)
    """

    # Mapeo de familia de modelo a nombre de encoding tiktoken
    _ENCODING_MAP: Dict[str, str] = {
        "claude": "cl100k_base",
        "gpt-4": "gpt-4",          # encoding_for_model, no get_encoding
        "gemini": "cl100k_base",    # mas cercano disponible
        "llama": "cl100k_base",     # mas cercano disponible
    }

    def __init__(self, model_family: str = "claude") -> None:
        """
        Args:
            model_family: Familia de modelo ("claude", "gpt-4", "gemini", "llama").
                          Por defecto "claude".
        """
        self.model_family = model_family
        self._cache: OrderedDict[str, int] = OrderedDict()
        self._cache_maxsize = 2048
        self._encoder = self._init_encoder()
        self._warned: bool = False

    # ------------------------------------------------------------------
    # Inicialización del encoder
    # ------------------------------------------------------------------

    def _init_encoder(self) -> Any:
        """
        Inicializa el encoder tiktoken según ``model_family``.

        Returns:
            Encoder tiktoken, o None si no está disponible.
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

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def count(self, text: str) -> int:
        """
        Cuenta tokens reales usando el tokenizador configurado.

        Resultados cacheados con LRU (max 2048 entradas) para evitar
        recalcular strings repetidos.

        Args:
            text: Texto a contar.

        Returns:
            Número estimado de tokens (mínimo 1).
        """
        if not text:
            return 1

        # Cache hit — mover al final (orden LRU)
        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]

        # Contar tokens con encoder real o fallback
        if self._encoder is not None:
            try:
                count = len(self._encoder.encode(text))
            except Exception:
                count = max(1, len(text) // 4)
        else:
            count = max(1, len(text) // 4)

        # Almacenar en cache LRU
        self._cache[text] = count
        if len(self._cache) > self._cache_maxsize:
            self._cache.popitem(last=False)

        return count

    def truncate_to_token_limit(self, text: str, max_tokens: int) -> str:
        """
        Trunca texto para que no exceda ``max_tokens``.

        Usa búsqueda binaria sobre prefijos para encontrar el punto
        de truncado óptimo respetando el límite de tokens.

        Args:
            text: Texto a truncar.
            max_tokens: Máximo de tokens permitidos (min 1).

        Returns:
            Texto truncado que cumple con el límite.
        """
        if not text or max_tokens < 1:
            return ""

        if self.count(text) <= max_tokens:
            return text

        # Búsqueda binaria del prefijo más largo dentro del límite
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
    frozen: bool = False  # True = no comprimir/truncar
    compressed: bool = False
    _token_estimator: Optional[TokenEstimator] = field(
        default=None, repr=False, compare=False
    )

    @property
    def token_estimate(self) -> int:
        """Estima tokens usando el tokenizador real si está disponible."""
        if self._token_estimator is not None:
            return self._token_estimator.count(self.content)
        return max(1, len(self.content) // int(CHARS_PER_TOKEN))

    @property
    def over_budget(self) -> bool:
        return self.token_estimate > self.max_tokens

    def truncate_to_budget(self) -> bool:
        """
        Trunca contenido al presupuesto.

        Usa el tokenizador real si está configurado, de lo contrario
        usa la heurística chars/4. Intenta preservar límites de párrafo.

        Returns:
            True si se truncó algo.
        """
        if self.frozen or not self.over_budget:
            return False

        if self._token_estimator is not None:
            # Truncado preciso basado en tokens reales
            current_len = len(self.content)
            truncated = self._token_estimator.truncate_to_token_limit(
                self.content, self.max_tokens
            )
            # Intentar cortar en límite de párrafo (10% margen)
            margin = int(current_len * 0.1)
            last_para = truncated.rfind("\n\n")
            if last_para > len(truncated) - margin:
                truncated = truncated[:last_para]
            self.content = truncated + "\n\n[...truncated...]"
        else:
            # Fallback: chars/4 con preservación de párrafos
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

class ContextWindowManager(StatsMixin):
    """
    Gestiona la ventana de contexto para llamadas LLM.

    Estrategias:
      1. Priority ordering: secciones criticas primero, fondo despues
      2. Budget allocation: cada seccion tiene un maximo de tokens
      3. Sliding window: mantener ultimos N mensajes completos
      4. Summarization: comprimir historial antiguo a resumen
      5. Section dropping: eliminar secciones de baja prioridad si es necesario
      6. Observation Masking: reemplazar tool outputs grandes con placeholders

    Incorpora ``TokenEstimator`` para conteo preciso de tokens
    con soporte multi-modelo (tiktoken + LRU cache).

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
        """
        Args:
            total_budget: Tokens maximos para la ventana completa.
            sliding_window_size: Mensajes completos a mantener.
            summary_fn: Funcion de resumen personalizada.
            model_family: Familia de modelo para TokenEstimator.
            use_real_tokenizer: Usar tokenizador real (tiktoken) si está disponible.
            use_observation_masking: Usar Observation Masking en tool outputs.
        """
        super().__init__()
        self._total_budget = total_budget
        self._sliding_window_size = sliding_window_size
        self._summary_fn = summary_fn or self._default_summary
        self._use_real_tokenizer = use_real_tokenizer
        self._use_observation_masking = use_observation_masking

        # Inicializar estimador de tokens
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
    # Helpers de tokenización
    # ------------------------------------------------------------------

    def _count_tokens(self, text: str) -> int:
        """
        Cuenta tokens usando el tokenizador configurado o fallback chars/4.

        Args:
            text: Texto a contar.

        Returns:
            Numero de tokens (minimo 1).
        """
        if self._use_real_tokenizer:
            return self._token_estimator.count(text)
        return max(1, len(text) // int(CHARS_PER_TOKEN))

    def _window_total_tokens(self, window: ContextWindow) -> int:
        """
        Calcula tokens totales de una ventana usando el tokenizador configurado.

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
        """
        Verifica si la ventana excede el presupuesto.

        Args:
            window: Ventana de contexto.

        Returns:
            True si supera el presupuesto.
        """
        return self._window_total_tokens(window) > window.total_budget

    def _section_over_budget(self, section: ContextSection) -> bool:
        """
        Verifica si una seccion excede su presupuesto de tokens.

        Args:
            section: Seccion a verificar.

        Returns:
            True si supera su max_tokens.
        """
        return self._count_tokens(section.content) > section.max_tokens

    def _inject_estimator(self, window: ContextWindow) -> None:
        """
        Inyecta el token estimator en todas las secciones de la ventana.

         Esto permite que ``ContextSection.token_estimate`` y
         ``ContextSection.truncate_to_budget()`` usen el tokenizador real.
        """
        if not self._use_real_tokenizer:
            return
        for section in window.sections.values():
            section._token_estimator = self._token_estimator

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def create_window(self) -> ContextWindow:
        """Create a new context window with the global budget."""
        return ContextWindow(total_budget=self._total_budget)

    def optimize(self, window: ContextWindow) -> ContextWindow:
        """
        Optimize a context window to fit within budget.

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
        # Inyectar estimador en las secciones
        self._inject_estimator(window)

        before = self._window_total_tokens(window)
        self._stats["optimizations"] += 1
        self._stats["tokens_before"] += before

        if not self._window_over_budget(window):
            self._stats["tokens_after"] += before
            return window

        # Strategy 1: Truncate over-budget sections (lowest priority first)
        over_budget_sections = sorted(
            [s for s in window.sections.values() if self._section_over_budget(s) and not s.frozen],
            key=lambda x: x.priority,
            reverse=True,  # Start with lowest priority
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
            if self._summarize_conversation(conv_section):
                self._stats["summarizations"] += 1

        # Strategy 3: Compress tool outputs (observation masking + fallback truncation)
        tool_section = window.get_section("tool_outputs")
        if tool_section and self._window_over_budget(window) and not tool_section.frozen:
            self._compress_tool_outputs(tool_section)

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
                    # Try compressing first
                    if self._count_tokens(section.content) > 50:
                        section.content = self._aggressive_compress(section.content)
                        logger.debug("Compressed section '%s' aggressively", name)
                    else:
                        window.remove_section(name)
                        self._stats["sections_dropped"] += 1
                        logger.debug("Dropped section '%s'", name)

        # Strategy 5: Hard truncate (last resort)
        if self._window_over_budget(window):
            window = self._hard_truncate(window)

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

    # get_stats() heredado de StatsMixin

    # ------------------------------------------------------------------
    # Internal optimization strategies
    # ------------------------------------------------------------------

    def _summarize_conversation(self, section: ContextSection) -> bool:
        """Summarize conversation history to fit within budget."""
        if not section.content:
            return False

        current_tokens = self._count_tokens(section.content)
        if current_tokens <= section.max_tokens:
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
        if self._count_tokens(section.content) > section.max_tokens:
            section.truncate_to_budget()

        return True

    def _compress_tool_outputs(self, section: ContextSection) -> bool:
        """
        Comprime tool outputs con Observation Masking primero, luego truncado legacy.

        Observation Masking (JetBrains 2026): reemplaza contenido extenso
        de herramientas con placeholders [tool_output:{name}:{id}], preservando
        metadata (status, duration) y primeras 3 lineas de contenido.

        Si tras el masking aun se excede el budget, cae en truncado clasico.
        """
        if not section.content:
            return False

        # Step 1: Observation Masking (placeholder inteligente)
        if self._use_observation_masking:
            masked = self._apply_observation_masking(section.content)
            if masked != section.content:
                section.content = masked
                section.compressed = True
                if not self._section_over_budget(section):
                    logger.debug(
                        "Observation masking applied to '%s', within budget",
                        section.name,
                    )
                    return True

        # Step 2: Legacy truncation (fallback si aun sobre budget)
        if not self._section_over_budget(section):
            return section.compressed

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
        max_tokens_limit = int(window.total_budget * 0.95)

        # Compute per-section token counts
        section_tokens = {
            name: self._count_tokens(s.content)
            for name, s in window.sections.items()
        }
        current_tokens = sum(section_tokens.values())

        # Build ordered list of sections by priority (lowest first)
        ordered = sorted(
            window.sections.items(),
            key=lambda x: (x[1].priority, section_tokens.get(x[0], 0)),
            reverse=True,
        )

        for name, section in ordered:
            if current_tokens <= max_tokens_limit:
                break
            if section.frozen:
                continue

            section_token_count = section_tokens.get(name, 0)
            if section.priority >= PRIORITY_LOW and section_token_count > 25:
                # Remove section entirely if low priority
                window.remove_section(name)
                current_tokens -= section_token_count
                logger.debug("Hard truncate: removed section '%s'", name)
            elif section_token_count > 5:
                # Heavy truncation
                keep_tokens = min(50, int(section.max_tokens * 0.5))
                if self._use_real_tokenizer:
                    section.content = self._token_estimator.truncate_to_token_limit(
                        section.content, max(1, keep_tokens)
                    ) + "\n[...]"
                else:
                    keep_chars = min(200, int(section.max_tokens * CHARS_PER_TOKEN * 0.5))
                    section.content = section.content[:keep_chars] + "\n[...]"
                section.compressed = True
                new_tokens = self._count_tokens(section.content)
                current_tokens = current_tokens - section_token_count + new_tokens
                logger.debug("Hard truncate: compressed section '%s'", name)

        return window

    # ------------------------------------------------------------------
    # Observation Masking (tecnica vanguardia 2026)
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_observation_masking(text: str, max_tokens: int = 500) -> str:
        """
        Observation Masking: reemplaza outputs grandes de herramientas con placeholders.

        Tecnica probada por JetBrains en 500 SWE-bench instances (2026).
        Supera a la summarizacion por LLM a una fraccion del costo.

        Identifica bloques de tool output por patrones (Tool:, >, Result:,
        Output:, Response:, Data:) y reemplaza el contenido interno extenso
        con placeholders [tool_output:{name}:{id}], preservando:
        - Metadata (Status:, Duration:, Time:, Error:, Exit:)
        - Primeras 3 lineas de contenido
        - Lineas de cabecera del tool

        Importante: dentro de un bloque iniciado por ``Tool:`` o ``>``, las
        lineas ``Result:``, ``Output:``, etc. se tratan como contenido, no
        como inicio de un nuevo bloque. Esto evita fragmentar la salida de
        una herramienta.

        Args:
            text: Texto a procesar.
            max_tokens: Si el texto tiene menos tokens estimados que esto,
                        se devuelve intacto (evita masking innecesario).

        Returns:
            Texto con observation masking aplicado.
        """
        char_limit = int(max_tokens * CHARS_PER_TOKEN)
        if len(text) <= char_limit:
            return text

        # Patron de inicio de bloque de tool output (todos los modos)
        tool_starter = re.compile(
            r'^\s*(?:Tool[:>\s]|>|Result[:>\s]|Output[:>\s]|Response[:>\s]|Data[:>\s])'
        )
        # Dentro de un bloque solo Tool: y > inician un nuevo bloque
        # (Result:, Output: etc. son contenido dentro del bloque)
        inner_tool_starter = re.compile(
            r'^\s*(?:Tool[:>\s]|>)'
        )
        # Patron de linea de metadata (siempre preservar)
        meta_pattern = re.compile(
            r'^\s*(Status|Duration|Time|Error|Exit)[:\s]'
        )

        lines = text.split('\n')
        result: List[str] = []
        i = 0
        block_counter = 0

        while i < len(lines):
            line = lines[i]
            if tool_starter.match(line.strip()):
                # Extraer nombre del tool
                tool_name = 'tool'
                stripped = line.strip().lower()
                for prefix in ('tool', 'result', 'output', 'response', 'data'):
                    if stripped.startswith(prefix):
                        tool_name = prefix
                        break

                result.append(line)  # Preservar cabecera
                i += 1

                meta_buf: List[str] = []
                content_buf: List[str] = []

                # Recolectar contenido del bloque
                # Dentro del bloque SOLO Tool: y > inician nuevo bloque
                while i < len(lines):
                    if inner_tool_starter.match(lines[i].strip()):
                        break  # Siguiente bloque (solo Tool: o >)
                    if meta_pattern.match(lines[i].strip()):
                        meta_buf.append(lines[i])
                    elif lines[i].strip():
                        content_buf.append(lines[i])
                    # Lineas vacias dentro del bloque se omiten
                    i += 1

                # Emitir metadata + primeras 3 lineas de contenido + placeholder
                result.extend(meta_buf)
                result.extend(content_buf[:3])
                if len(content_buf) > 3:
                    result.append(f'[tool_output:{tool_name}:{block_counter}]')
                    block_counter += 1
            else:
                result.append(line)
                i += 1

        return '\n'.join(result)

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
