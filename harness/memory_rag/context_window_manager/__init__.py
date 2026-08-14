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

Refactorizado a paquete (regla AGR: archivo < 500 lineas). Todos los
simbolos publicos del modulo original se re-exportan desde aqui, por lo
que los imports existentes
(``from harness.memory_rag.context_window_manager import ContextWindowManager``)
siguen funcionando identicos.
"""
from __future__ import annotations

from .constants import (
    DEFAULT_BUDGETS,
    MAX_SUMMARY_CHARS,
    PRIORITY_BACKGROUND,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    SECTION_PRIORITIES,
    SLIDING_WINDOW_SIZE,
)
from .estimator import TokenEstimator
from .manager import ContextWindowManager
from .sections import ContextSection
from .window import ContextWindow

__all__ = [
    "DEFAULT_BUDGETS",
    "MAX_SUMMARY_CHARS",
    "PRIORITY_BACKGROUND",
    "PRIORITY_CRITICAL",
    "PRIORITY_HIGH",
    "PRIORITY_LOW",
    "PRIORITY_NORMAL",
    "SECTION_PRIORITIES",
    "SLIDING_WINDOW_SIZE",
    "ContextSection",
    "ContextWindow",
    "ContextWindowManager",
    "TokenEstimator",
]
