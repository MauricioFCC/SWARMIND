"""
Prompt Cache Builder — Construye prompts optimizados para cache de proveedores LLM.

Basado en mejores prácticas 2026 de prompt caching (Anthropic, OpenAI, Gemini):
  - Stable prefix first: identidad del sistema, reglas, schemas de tools
  - Variable suffix last: mensaje del usuario, contexto actual
  - Cache markers: puntos de interrupcion de cache compatibles con Anthropic
  - Cache-friendly RAG: contexto recuperado despues del marker de cache

Ahorro estimado: 50-90% en tokens de input para llamadas repetitivas.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Cache markers para Anthropic (https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
CACHE_MARKER_BREAKPOINT = "cache_control:breakpoint"
CACHE_MARKER_EPHEMERAL = "cache_control:ephemeral"

# Secciones estables vs variables
STABLE_SECTIONS = [
    "system_identity",
    "system_rules",
    "system_guardrails",
    "tool_definitions",
    "output_schema",
    "skill_catalog",  # Tier 1 skills (nombres)
]

VARIABLE_SECTIONS = [
    "user_message",
    "rag_context",
    "conversation_history",
    "loaded_skills",
    "session_context",
    "tool_outputs",
]

# Cache hit requirements (segun providers 2026):
#   Anthropic: minimo 1024 tokens antes del breakpoint
#   OpenAI: automatico, minimo 1024 tokens de prefix
MIN_CACHE_PREFIX_TOKENS = 1024


# ---------------------------------------------------------------------------
# Prompt Structure
# ---------------------------------------------------------------------------

@dataclass
class CacheSection:
    """A section of the prompt with cache awareness."""
    name: str
    content: str
    stable: bool = True          # True = parte del prefix cacheable
    cache_breakpoint: bool = False  # True = insertar marker de cache aqui
    estimated_tokens: int = 0

    @property
    def is_cacheable(self) -> bool:
        """Section can be cached if it's stable and has content."""
        return self.stable and bool(self.content.strip())

    @property
    def is_variable(self) -> bool:
        """Section changes between requests."""
        return not self.stable


# ---------------------------------------------------------------------------
# Prompt Cache Builder
# ---------------------------------------------------------------------------

class PromptCacheBuilder:
    """
    Construye prompts optimizados para cache de LLM providers.

    Estrategia:
      1. Stable prefix: todo el contenido fijo (system prompt, reglas, tools)
      2. Cache breakpoint: marker explicito para Anthropic
      3. Variable suffix: contenido que cambia por request
      4. Prefix padding: si el prefix es muy corto, auto-padding para alcanzar
         el minimo de cache (1024 tokens)

    Uso:
        builder = PromptCacheBuilder()
        prompt = builder.build(
            system_identity="You are...",
            system_rules="...",
            user_message="Hola",
            rag_context="...",
        )
        # prompt tiene [CACHE_BREAKPOINT] entre secciones estables y variables
    """

    def __init__(
        self,
        min_cache_prefix: int = MIN_CACHE_PREFIX_TOKENS,
        use_cache_markers: bool = True,
        provider: str = "anthropic",  # anthropic, openai, gemini
    ) -> None:
        self._min_cache_prefix = min_cache_prefix
        self._use_cache_markers = use_cache_markers
        self._provider = provider.lower()
        self._stats: dict[str, Any] = {
            "builds": 0,
            "cacheable_prefix_tokens": 0,
            "variable_suffix_tokens": 0,
            "total_tokens": 0,
            "cache_hit_eligible": False,
            "padding_added": 0,
        }

        logger.info(
            "PromptCacheBuilder initialized (provider=%s, min_prefix=%d)",
            provider, min_cache_prefix,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        *,
        system_identity: str = "",
        system_rules: str = "",
        system_guardrails: str = "",
        tool_definitions: str = "",
        output_schema: str = "",
        skill_catalog: str = "",
        user_message: str = "",
        rag_context: str = "",
        conversation_history: str = "",
        loaded_skills: str = "",
        session_context: str = "",
        tool_outputs: str = "",
        **extra_sections: str,
    ) -> str:
        """
        Build a cache-optimized prompt.

        Args:
            system_identity: Who the AI is.
            system_rules: Core behavioral rules.
            system_guardrails: Safety constraints.
            tool_definitions: Tool/function schemas.
            output_schema: Expected output format.
            skill_catalog: Available skills (tier 1 names).
            user_message: The user's current message.
            rag_context: Retrieved documents.
            conversation_history: Previous messages.
            loaded_skills: Loaded skill content (tier 2/3).
            session_context: Current session state.
            tool_outputs: Results from tool calls.
            **extra_sections: Additional named sections.

        Returns:
            Cache-optimized prompt string.
        """
        char_count = 0

        # --- STABLE PREFIX (cached) ---
        stable_contents = []

        if system_identity:
            stable_contents.append(("system_identity", system_identity, True))
        if system_rules:
            stable_contents.append(("system_rules", system_rules, True))
        if system_guardrails:
            stable_contents.append(("system_guardrails", system_guardrails, True))
        if tool_definitions:
            stable_contents.append(("tool_definitions", tool_definitions, True))
        if output_schema:
            stable_contents.append(("output_schema", output_schema, True))
        if skill_catalog:
            stable_contents.append(("skill_catalog", skill_catalog, True))

        # Add extra stable sections
        for name, content in extra_sections.items():
            if name.startswith("stable_"):
                stable_contents.append((name, content, True))

        # Build stable prefix
        stable_parts: list[str] = []
        for name, content, _ in stable_contents:
            stable_parts.append(content)
            char_count += len(content)

        stable_prefix = "\n\n".join(stable_parts)
        prefix_tokens = char_count // 4

        # --- Cache breakpoint ---
        cache_breakpoint = ""
        if self._use_cache_markers:
            # Asegurar que el prefix alcance el minimo de cache
            if prefix_tokens < self._min_cache_prefix and stable_prefix:
                padding_needed = self._min_cache_prefix - prefix_tokens
                # Add padding to reach minimum (repetir ultima linea significativa)
                last_section = stable_contents[-1][1] if stable_contents else ""
                if last_section:
                    # Extraer ultimas palabras significativas como padding
                    words = last_section.split()
                    padding_text = " ".join(words[-20:]) if len(words) > 20 else last_section
                    # Repetir hasta alcanzar el minimo
                    repeats = max(1, padding_needed // (len(padding_text) // 4 + 1))
                    padding = f"\n\n# Cache padding\n{padding_text}\n" * min(repeats, 5)
                    stable_prefix += padding
                    self._stats["padding_added"] += len(padding) // 4
                    char_count += len(padding)
                    prefix_tokens = char_count // 4

            cache_breakpoint = f"\n[{CACHE_MARKER_BREAKPOINT}]\n"

        # --- VARIABLE SUFFIX (not cached) ---
        variable_parts: list[str] = []
        var_contents = []

        if session_context:
            var_contents.append(("session_context", session_context, False))
        if loaded_skills:
            var_contents.append(("loaded_skills", loaded_skills, False))
        if conversation_history:
            var_contents.append(("conversation_history", conversation_history, False))
        if rag_context:
            var_contents.append(("rag_context", rag_context, False))
        if tool_outputs:
            var_contents.append(("tool_outputs", tool_outputs, False))
        if user_message:
            var_contents.append(("user_message", user_message, False))

        # Add extra variable sections
        for name, content in extra_sections.items():
            if name.startswith("variable_"):
                var_contents.append((name, content, False))

        for name, content, _ in var_contents:
            variable_parts.append(content)

        variable_suffix = "\n\n".join(variable_parts)
        suffix_tokens = len(variable_suffix) // 4

        # --- Assemble ---
        prompt_parts = [stable_prefix]
        if cache_breakpoint:
            prompt_parts.append(cache_breakpoint)
        if variable_suffix:
            prompt_parts.append(variable_suffix)

        full_prompt = "\n".join(prompt_parts)

        # Stats
        self._stats["builds"] += 1
        self._stats["cacheable_prefix_tokens"] = prefix_tokens
        self._stats["variable_suffix_tokens"] = suffix_tokens
        self._stats["total_tokens"] = prefix_tokens + suffix_tokens
        self._stats["cache_hit_eligible"] = prefix_tokens >= self._min_cache_prefix

        return full_prompt

    def build_chat_messages(
        self,
        system_content: str,
        messages: list[dict[str, str]],
        cache_system: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Build cache-optimized chat messages for chat-style APIs.

        Para Anthropic: coloca el cache breakpoint en el penultimo mensaje.
        Para OpenAI: estructura el system prompt como prefix largo.

        Args:
            system_content: System prompt content.
            messages: List of {"role": ..., "content": ...} messages.
            cache_system: Whether to mark system message as cacheable.

        Returns:
            Messages list with cache markers.
        """
        if self._provider == "anthropic" and cache_system:
            # Anthropic supports per-message cache control
            result: list[dict[str, Any]] = []

            # System message with cache breakpoint
            result.append({
                "role": "system",
                "content": system_content,
                CACHE_MARKER_EPHEMERAL: True,  # Anthropic cache marker
            })

            # User messages (last one gets no cache marker if short)
            for i, msg in enumerate(messages):
                if i == len(messages) - 1 and len(messages) > 1:
                    # Last message: no cache marker (variable)
                    result.append(msg)
                else:
                    result.append({
                        **msg,
                        CACHE_MARKER_EPHEMERAL: True,
                    })

            return result

        elif self._provider == "openai":
            # OpenAI: automatic prefix caching, just structure well
            result = [{"role": "system", "content": system_content}]
            result.extend(messages)
            return result

        else:
            # Generic: no cache markers
            return [{"role": "system", "content": system_content}] + messages

    # ------------------------------------------------------------------
    # Cache optimization utilities
    # ------------------------------------------------------------------

    def estimate_cache_savings(
        self,
        prompt: str,
        num_calls: int = 100,
    ) -> dict[str, Any]:
        """
        Estimate token savings from prompt caching.

        Args:
            prompt: The full prompt to analyze.
            num_calls: Number of calls to simulate.

        Returns:
            Dict with savings estimates.
        """
        total_tokens = len(prompt) // 4

        # Find cache boundary (between stable and variable)
        breakpoint_idx = prompt.find(f"[{CACHE_MARKER_BREAKPOINT}]")
        if breakpoint_idx >= 0:
            stable_tokens = len(prompt[:breakpoint_idx]) // 4
            variable_tokens = len(prompt[breakpoint_idx:]) // 4
        else:
            # Estimate: first 70% likely stable
            stable_tokens = int(total_tokens * 0.7)
            variable_tokens = total_tokens - stable_tokens

        # Sin cache
        cost_without_cache = total_tokens * num_calls

        # Con cache (stable prefix cached, only pay for variable + generation)
        cost_with_cache = stable_tokens * 0.1 * num_calls + variable_tokens * num_calls
        # Nota: 0.1 = 90% discount on cached tokens (Anthropic pricing)

        savings = cost_without_cache - cost_with_cache
        savings_pct = (1 - cost_with_cache / max(cost_without_cache, 1)) * 100

        return {
            "total_tokens_per_call": total_tokens,
            "stable_prefix_tokens": stable_tokens,
            "variable_suffix_tokens": variable_tokens,
            "num_calls": num_calls,
            "cost_without_cache_tokens": cost_without_cache,
            "cost_with_cache_tokens": round(cost_with_cache),
            "savings_tokens": round(savings),
            "savings_pct": round(savings_pct, 1),
            "cache_eligible": stable_tokens >= self._min_cache_prefix,
        }

    @staticmethod
    def optimize_for_caching(prompt: str) -> str:
        """
        Reorganize an existing prompt for better cache performance.

        Moves stable content to the beginning and variable content to the end.
        """
        # Simple heuristic: find where user-specific content starts
        # (conversation history, user message, etc.)
        variable_markers = [
            "User Message:", "User:", "Human:", "### Conversation",
            "### Context", "rag_context", "conversation_history",
        ]

        lines = prompt.split("\n")
        split_idx = len(lines)

        for i, line in enumerate(lines):
            for marker in variable_markers:
                if marker.lower() in line.lower() and i > len(lines) * 0.3:  # Only split after first 30%
                    split_idx = i
                    break
            if split_idx < len(lines):
                break

        stable = "\n".join(lines[:split_idx])
        variable = "\n".join(lines[split_idx:])

        return f"{stable}\n\n[CACHE_BREAKPOINT]\n\n{variable}"

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return builder statistics."""
        stats = dict(self._stats)
        if stats.get("builds", 0) > 0:
            stats["avg_prefix_tokens"] = round(
                stats["cacheable_prefix_tokens"] / max(stats["builds"], 1)
            )
            stats["avg_total_tokens"] = round(
                stats["total_tokens"] / max(stats["builds"], 1)
            )
        return stats
