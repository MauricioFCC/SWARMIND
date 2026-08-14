"""Constantes para el paquete ``context_assembler``.

Extraido mecanicamente de ``context_assembler.py`` (regla AGR < 500
lineas). Contiene la dimension del embedding por defecto y las
constantes del retrieval adaptivo (adaptive-k).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default embedding model dimension for fallback random vectors
_EMBEDDING_DIM = 384

# Adaptive-k retrieval constants
_ADAPTIVE_K_DEFAULT = 10
_ADAPTIVE_K_MIN = 2
_ADAPTIVE_K_MAX = 15
_ADAPTIVE_K_GAP_THRESHOLD = 0.15  # gap de score para cortar
_ADAPTIVE_K_HIGH_CONFIDENCE = 0.93  # score para considerar "muy buena" recuperacion
