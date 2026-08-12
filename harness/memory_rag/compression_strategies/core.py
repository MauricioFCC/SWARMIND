"""Clase principal ``CompressionStrategies`` para el paquete homonimo.

Extraido mecanicamente de ``compression_strategies.py`` (regla AGR < 500
lineas). La clase se dividio en mixins cohesivos (normalization,
structured, detection, text_heuristics) que se componen aqui para
conservar exactamente la misma API publica y privada que el modulo
original. ``PromptCompressor`` hereda de ``CompressionStrategies`` sin
ningun cambio en sus imports.
"""
from __future__ import annotations

from .detection import _MethodDetectionMixin
from .normalization import _NormalizationMixin
from .structured import _StructuredCompressionMixin
from .text_heuristics import _TextHeuristicsMixin


class CompressionStrategies(
    _NormalizationMixin,
    _StructuredCompressionMixin,
    _MethodDetectionMixin,
    _TextHeuristicsMixin,
):
    """Mixin con estrategias de compresion (hereda PromptCompressor hereda de esta)."""
