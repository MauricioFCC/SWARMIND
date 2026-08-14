"""Constantes para el paquete ``compression_strategies``.

Extraido mecanicamente de ``compression_strategies.py`` (regla AGR < 500
lineas). Contiene las claves preservadas en compresion estructurada.
"""
from __future__ import annotations

# Keys whose values should not be truncated in YAML/JSON compression
STRUCTURED_PRESERVE_KEYS: set[str] = {
    "name", "description", "version", "title", "summary",
    "instruction", "goal", "purpose", "constraint",
}
