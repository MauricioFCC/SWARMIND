"""Mixin de compresion estructurada para ``CompressionStrategies``.

Extraido mecanicamente de ``compression_strategies.py`` (regla AGR < 500
lineas). Contiene los metodos de compresion de JSON/YAML preservando
keys criticas.
"""
from __future__ import annotations

import json
import logging
import re

from .constants import STRUCTURED_PRESERVE_KEYS

logger = logging.getLogger("harness.memory_rag.compression_strategies")


class _StructuredCompressionMixin:
    """Metodos de compresion de texto estructurado (JSON/YAML)."""

    def _structured_compress(self, text: str, ratio: float) -> str:
        """
        Comprime texto estructurado (JSON/YAML) preservando keys criticas.

        WHAT: Comprime schemas JSON y YAML eliminando whitespace innecesario,
        acortando keys no criticas, y compactando arrays y objetos.
        WHY: Los schemas estructurados suelen tener mucho whitespace y
        keys descriptivas largas que pueden acortarse sin perder semantica.
        WHERE: Schemas de tools, configuraciones YAML, JSON prompts.

        Args:
            text: Texto estructurado a comprimir.
            ratio: Proporcion objetivo.

        Returns:
            Texto estructurado comprimido.
        """
        if not text:
            return ""

        # Detectar si es JSON o YAML
        is_json = text.strip().startswith(("{", "["))
        if is_json:
            return self._compress_json(text, ratio)
        else:
            return self._compress_yaml(text, ratio)

    def _compress_json(self, text: str, ratio: float) -> str:
        """
        Comprime un JSON (o JSON-like) preservando estructura.

        Args:
            text: Texto JSON a comprimir.
            ratio: Proporcion objetivo.

        Returns:
            JSON comprimido.
        """
        try:
            parsed = json.loads(text)
            # Compactar: separadores minimos
            compact = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)

            # Si aun excede el target, acortar strings largos
            if ratio < 0.5 and self._count_tokens(compact) > self._count_tokens(text) * ratio:
                compact = self._truncate_json_strings(compact, ratio)

            return compact
        except json.JSONDecodeError:
            # No es JSON valido: aplicar extractive estandar
            logger.debug(
                "Structured: JSON invalido, usando extractive en su lugar"
            )
            return self.extractive_compress(text, ratio)

    def _compress_yaml(self, text: str, ratio: float) -> str:
        """
        Comprime texto YAML preservando estructura jerarquica.

        Args:
            text: Texto YAML a comprimir.
            ratio: Proporcion objetivo.

        Returns:
            YAML comprimido.
        """
        lines = text.split("\n")
        compressed: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Preservar comentarios importantes (# TODO, # NOTE, # SECURITY)
            if stripped.startswith("#") and not any(
                kw in stripped.upper() for kw in ("TODO", "NOTE", "SECURITY", "FIXME", "HACK")
            ):
                continue  # Eliminar comentarios no criticos

            # Acortar valores largos en una linea
            if ":" in stripped and not stripped.startswith("-"):
                key, _, value = stripped.partition(":")
                key_stripped = key.strip()
                value_stripped = value.strip()

                # Si el valor es largo, truncar
                if len(value_stripped) > 100 and key_stripped not in STRUCTURED_PRESERVE_KEYS:
                    value_stripped = value_stripped[:80] + "..."

                compressed.append(f"{key_stripped}: {value_stripped}")
            else:
                compressed.append(stripped)

        return "\n".join(compressed)

    def _truncate_json_strings(self, json_str: str, ratio: float) -> str:
        """
        Trunca strings largos dentro de un JSON.

        Args:
            json_str: JSON string.
            ratio: Ratio de compresion.

        Returns:
            JSON con strings truncados.
        """
        # Estrategia: reemplazar strings de mas de 50 chars con version truncada
        def truncate_match(m: re.Match) -> str:
            full = m.group(0)
            # Extraer el string interno (sin comillas)
            inner = full[1:-1]
            if len(inner) > 50:
                truncated = inner[:40] + "..."
                return f'"{truncated}"'
            return full

        return re.sub(r'"[^"]{50,}"', truncate_match, json_str)
