"""
Context assembly for agents.

The ``ContextAssembler`` takes a user message and agent role, searches the
vector store for relevant RAG chunks, fetches recent task history, and
produces a structured context dict that fits within a token budget.

OPTIMIZACIONES:
- Parallel RAG: ``assemble_async()`` ejecuta busquedas RAG + task context
  en PARALELO via ``asyncio.gather()``, reduciendo latencia ~40-50%.
- Token Budget: ``_estimate_tokens()`` usa ``tiktoken`` si esta disponible
  para conteo preciso de tokens, con fallback a chars/4.
- Token warning: se loguea advertencia cuando se excede el budget,
  y se trunca con 10% de margen de seguridad.

Refactorizado a paquete (regla AGR: archivo < 500 lineas). Todos los
simbolos publicos del modulo original se re-exportan desde aqui, por lo
que los imports existentes
(``from harness.memory_rag.context_assembler import ContextAssembler``)
y los parches ``patch("harness.memory_rag.context_assembler.ContextAssembler")``
siguen funcionando identicos.
"""
from __future__ import annotations

from .constants import (
    _ADAPTIVE_K_DEFAULT,
    _ADAPTIVE_K_GAP_THRESHOLD,
    _ADAPTIVE_K_HIGH_CONFIDENCE,
    _ADAPTIVE_K_MAX,
    _ADAPTIVE_K_MIN,
    _EMBEDDING_DIM,
)
from .core import ContextAssembler
from .models import ContextAssembly

__all__ = [
    "_ADAPTIVE_K_DEFAULT",
    "_ADAPTIVE_K_GAP_THRESHOLD",
    "_ADAPTIVE_K_HIGH_CONFIDENCE",
    "_ADAPTIVE_K_MAX",
    "_ADAPTIVE_K_MIN",
    "_EMBEDDING_DIM",
    "ContextAssembler",
    "ContextAssembly",
]
