"""CompressionStrategies - Implementation strategies for prompt compression.

Refactorizado a paquete (regla AGR: archivo < 500 lineas). Todos los
simbolos publicos del modulo original se re-exportan desde aqui, por lo
que los imports existentes
(``from harness.memory_rag.compression_strategies import CompressionStrategies``)
siguen funcionando identicos.
"""
from __future__ import annotations

from .constants import STRUCTURED_PRESERVE_KEYS
from .core import CompressionStrategies

__all__ = [
    "STRUCTURED_PRESERVE_KEYS",
    "CompressionStrategies",
]
