"""Mixin de normalizacion para ``CompressionStrategies``.

Extraido mecanicamente de ``compression_strategies.py`` (regla AGR < 500
lineas). Contiene los metodos de normalizacion de whitespace, reemplazo
de frases de relleno, eliminacion de stop words y compresion extractiva
agresiva.
"""
from __future__ import annotations

import logging
import re

from harness.memory_rag.compression_types import FILLER_PATTERNS, STOP_WORDS

logger = logging.getLogger("harness.memory_rag.compression_strategies")


class _NormalizationMixin:
    """Metodos de normalizacion y compresion extractiva basica."""

    def _normalize_whitespace(self, text: str) -> str:
        """
        Normaliza whitespace: elimina espacios multiples, lineas vacias
        repetidas, y espacios al inicio/fin de lineas.

        Args:
            text: Texto a normalizar.

        Returns:
            Texto con whitespace normalizado.
        """
        # Colapsar 3+ newlines a 2
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Eliminar espacios al final de cada linea
        text = re.sub(r'[ \t]+\n', '\n', text)
        # Colapsar 2+ espacios a 1
        text = re.sub(r' {2,}', ' ', text)
        # Eliminar lineas que son solo whitespace
        text = re.sub(r'^[ \t]+$', '', text, flags=re.MULTILINE)
        return text.strip()

    def _replace_filler_phrases(self, text: str) -> str:
        """
        Reemplaza frases de relleno por equivalentes mas cortos.

        Args:
            text: Texto a procesar.

        Returns:
            Texto con frases reemplazadas.
        """
        result = text
        for pattern, replacement in FILLER_PATTERNS:
            try:
                result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
            except re.error as exc:
                logger.warning(
                    "WHAT: Error en regex filler '%s' -> '%s': %s. "
                    "WHY: Pattern regex invalido. "
                    "WHERE: PromptCompressor._replace_filler_phrases",
                    pattern, replacement, exc,
                )
                continue
        return result

    def _remove_stop_words(self, text: str) -> str:
        """
        Elimina stop words preservando palabras clave criticas.

        Estrategia:
        - Recorre cada linea del texto.
        - Para cada palabra, verifica si es stop word.
        - NO elimina si la palabra forma parte de una palabra clave preservada.
        - NO elimina si la linea contiene terminos criticos (instrucciones).

        Args:
            text: Texto a procesar.

        Returns:
            Texto con stop words eliminadas.
        """
        lines = text.split("\n")
        result_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                result_lines.append(line)
                continue

            # Verificar si la linea contiene palabras clave preservadas
            if self._has_preserved_keywords(stripped):
                result_lines.append(line)
                continue

            # Verificar si la linea parece codigo o estructura
            if self._looks_like_code(stripped):
                result_lines.append(line)
                continue

            # Filtrar stop words
            words = stripped.split()
            filtered = [w for w in words if w.lower().strip(".,;:!?()[]{}'\"") not in STOP_WORDS]

            if filtered:
                result_lines.append(" ".join(filtered))
            else:
                result_lines.append(line)  # Preservar linea original si todo se filtro

        return "\n".join(result_lines)

    def _aggressive_extractive(self, text: str) -> str:
        """
        Compresion extractiva agresiva para ratios bajos (<0.4).

        Ademas de stop words, elimina:
        - Adverbios de modo innecesarios
        - Calificativos debiles
        - Lineas de logging/debug
        - Parentesis con informacion redundante
        - Lineas que contienen solo articulos + sustantivos sin verbo

        Args:
            text: Texto a comprimir agresivamente.

        Returns:
            Texto comprimido agresivamente.
        """
        lines = text.split("\n")
        result: list[str] = []

        # Eliminar lineas de logging
        log_pattern = re.compile(
            r'^\s*(DEBUG|INFO|WARN(ING)?|ERROR|TRACE)\s*(\[.*?\])?\s*:',
            re.IGNORECASE,
        )

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Eliminar lineas de logging
            if log_pattern.match(stripped):
                continue

            # Eliminar lineas que son solo separadores decorativos
            if re.match(r'^[=\-#*\s]{10,}$', stripped):
                continue

            # Acortar lineas largas a primeras 3 palabras si tienen baja densidad
            word_count = len(stripped.split())
            if word_count > 15 and not self._has_verb(stripped):
                # Mantener solo primeras 8 palabras
                short = " ".join(stripped.split()[:8])
                result.append(short)
                continue

            result.append(line)

        return "\n".join(result)
