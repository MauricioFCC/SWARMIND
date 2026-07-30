"""
context_compression — Estrategias de compresion de ventana de contexto.

Extraido de context_window_manager.py para mantener modulos < 900 lines.

Incluye:
    - Summarization de conversacion
    - Observation Masking (JetBrains 2026)
    - Compresion agresiva de tool outputs
    - Hard truncation (last resort)
    - Default summary
    - Message summarization
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from harness.common import CHARS_PER_TOKEN

logger = logging.getLogger(__name__)

# Resumen de conversacion: chars max
MAX_SUMMARY_CHARS = 500

# Sliding window: mantener ultimos N mensajes completos
SLIDING_WINDOW_SIZE = 6


def summarize_conversation(
    self: Any,
    section: Any,
) -> bool:
    """Summarize conversation history to fit within budget.

    Args:
        self: Instancia de ContextWindowManager.
        section: ContextSection con el historial de conversacion.

    Returns:
        True si se comprimio algo.
    """
    if not section.content:
        return False

    current_tokens = self._count_tokens(section.content)
    if current_tokens <= section.max_tokens:
        return False

    # Split into messages
    messages = section.content.split("\n\n")
    if len(messages) <= 3:
        section.truncate_to_budget()
        return True

    # Keep last N messages, summarize rest
    keep_count = min(SLIDING_WINDOW_SIZE, len(messages) - 1)
    keep = messages[-keep_count:]
    summarize_chunk = messages[:-keep_count]

    summary = _default_summary_fn("\n".join(summarize_chunk))
    section.content = (
        f"[COMPACTED - {len(summarize_chunk)} previous messages]\n"
        f"{summary}\n\n"
        + "\n\n".join(keep)
    )
    section.compressed = True

    if self._count_tokens(section.content) > section.max_tokens:
        section.truncate_to_budget()

    return True


def compress_tool_outputs(
    self: Any,
    section: Any,
) -> bool:
    """Comprime tool outputs con Observation Masking primero, luego truncado legacy.

    Observation Masking (JetBrains 2026): reemplaza contenido extenso
    de herramientas con placeholders [tool_output:{name}:{id}], preservando
    metadata (status, duration) y primeras 3 lineas de contenido.

    Args:
        self: Instancia de ContextWindowManager.
        section: ContextSection con tool outputs.

    Returns:
        True si se comprimio algo.
    """
    if not section.content:
        return False

    # Step 1: Observation Masking
    if getattr(self, '_use_observation_masking', False):
        masked = _apply_observation_masking(section.content)
        if masked != section.content:
            section.content = masked
            section.compressed = True
            if not _section_over_budget(self, section):
                logger.debug(
                    "Observation masking applied to '%s', within budget",
                    section.name,
                )
                return True

    # Step 2: Legacy truncation (fallback)
    if not _section_over_budget(self, section):
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


def hard_truncate(
    self: Any,
    window: Any,
) -> Any:
    """Last resort: hard truncate at token limit.

    Removes content from lowest priority sections first.

    Args:
        self: Instancia de ContextWindowManager.
        window: ContextWindow a truncar.

    Returns:
        ContextWindow truncado.
    """
    from harness.memory_rag.context_window_manager import (
        PRIORITY_LOW,
        PRIORITY_BACKGROUND,
    )

    max_tokens_limit = int(window.total_budget * 0.95)

    section_tokens = {
        name: self._count_tokens(s.content)
        for name, s in window.sections.items()
    }
    current_tokens = sum(section_tokens.values())

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
            window.remove_section(name)
            current_tokens -= section_token_count
            logger.debug("Hard truncate: removed section '%s'", name)
        elif section_token_count > 5:
            keep_tokens = min(50, int(section.max_tokens * 0.5))
            if getattr(self, '_use_real_tokenizer', False) and self._token_estimator is not None:
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


def _apply_observation_masking(text: str, max_tokens: int = 500) -> str:
    """Observation Masking: reemplaza outputs grandes de herramientas con placeholders.

    Tecnica probada por JetBrains en 500 SWE-bench instances (2026).
    Supera a la summarizacion por LLM a una fraccion del costo.

    Identifica bloques de tool output por patrones (Tool:, >, Result:,
    Output:, Response:, Data:) y reemplaza el contenido interno extenso
    con placeholders [tool_output:{name}:{id}], preservando:
    - Metadata (Status:, Duration:, Time:, Error:, Exit:)
    - Primeras 3 lineas de contenido
    - Lineas de cabecera del tool

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

    tool_starter = re.compile(
        r'^\s*(?:Tool[:>\s]|>|Result[:>\s]|Output[:>\s]|Response[:>\s]|Data[:>\s])'
    )
    inner_tool_starter = re.compile(
        r'^\s*(?:Tool[:>\s]|>)'
    )
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
            tool_name = 'tool'
            stripped = line.strip().lower()
            for prefix in ('tool', 'result', 'output', 'response', 'data'):
                if stripped.startswith(prefix):
                    tool_name = prefix
                    break

            result.append(line)
            i += 1

            meta_buf: List[str] = []
            content_buf: List[str] = []

            while i < len(lines):
                if inner_tool_starter.match(lines[i].strip()):
                    break
                if meta_pattern.match(lines[i].strip()):
                    meta_buf.append(lines[i])
                elif lines[i].strip():
                    content_buf.append(lines[i])
                i += 1

            result.extend(meta_buf)
            result.extend(content_buf[:3])
            if len(content_buf) > 3:
                result.append(f'[tool_output:{tool_name}:{block_counter}]')
                block_counter += 1
        else:
            result.append(line)
            i += 1

    return '\n'.join(result)


def aggressive_compress(text: str) -> str:
    """Compress text aggressively by removing redundant whitespace/lines.

    Args:
        text: Texto a comprimir.

    Returns:
        Texto comprimido (max 1000 chars).
    """
    lines = [l for l in text.split("\n") if l.strip()]
    text_compressed = "\n".join(lines)
    text_compressed = re.sub(r" {2,}", " ", text_compressed)
    return text_compressed[:1000]


def _default_summary_fn(text: str) -> str:
    """Default summarization: extract first meaningful lines.

    Args:
        text: Texto a resumir.

    Returns:
        Resumen de maximo MAX_SUMMARY_CHARS caracteres.
    """
    text = text.strip()
    if len(text) <= MAX_SUMMARY_CHARS:
        return text
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    summary_lines: List[str] = []
    char_count = 0
    for line in lines:
        char_count += len(line) + 1
        if char_count > MAX_SUMMARY_CHARS:
            break
        summary_lines.append(line)
    return " | ".join(summary_lines) if summary_lines else text[:MAX_SUMMARY_CHARS]


def summarize_messages(messages: List[Dict[str, Any]]) -> str:
    """Summarize a list of messages.

    Args:
        messages: Lista de mensajes con 'role' y 'content'.

    Returns:
        Resumen textual de los mensajes.
    """
    key_points: List[str] = []
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            if len(content) > 150:
                content = content[:150] + "..."
            key_points.append(f"[{role}] {content}")
    return " | ".join(key_points) if key_points else "(history compressed)"


def _section_over_budget(self: Any, section: Any) -> bool:
    """Verifica si una seccion excede su presupuesto de tokens.

    Args:
        self: Instancia de ContextWindowManager.
        section: ContextSection a verificar.

    Returns:
        True si supera su max_tokens.
    """
    return self._count_tokens(section.content) > section.max_tokens
