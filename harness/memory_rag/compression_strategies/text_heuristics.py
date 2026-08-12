"""Mixin de heuristica textual para ``CompressionStrategies``.

Extraido mecanicamente de ``compression_strategies.py`` (regla AGR < 500
lineas). Contiene heuristicas de texto: palabras clave preservadas,
verbos, deteccion de codigo, lineas de stop words y enforcement del
ratio objetivo.
"""
from __future__ import annotations

import re

from harness.memory_rag.compression_types import CHARS_PER_TOKEN, PRESERVED_KEYWORDS, STOP_WORDS


class _TextHeuristicsMixin:
    """Heuristicas de analisis textual para la compresion."""

    def _has_preserved_keywords(self, text: str) -> bool:
        """
        Verifica si un texto contiene palabras clave que deben preservarse.

        Args:
            text: Texto a verificar.

        Returns:
            True si contiene palabras clave preservadas.
        """
        lower = text.lower()
        for keyword in PRESERVED_KEYWORDS:
            if keyword in lower:
                return True
        return False

    def _has_verb(self, text: str) -> bool:
        """
        Heuristico simple: verifica si el texto contiene verbos comunes.

        Args:
            text: Texto a verificar.

        Returns:
            True si contiene al menos un verbo conocido.
        """
        verbs = {
            "es", "son", "fue", "era", "ser", "estar", "tener", "hacer",
            "puede", "debe", "va", "dice", "tiene", "estan", "esta",
            "is", "are", "was", "were", "be", "have", "has", "do",
            "does", "can", "must", "will", "would", "shall", "may",
            "need", "use", "uses", "used", "using",
            "crea", "crear", "creado", "genera", "generar", "generado",
            "procesa", "procesar", "procesado", "ejecuta", "ejecutar",
            "ejecutado", "obtiene", "obtener", "obtenido", "devuelve",
            "devolver", "devuelto", "define", "definir", "definido",
        }
        words = set(text.lower().split())
        return bool(words & verbs)

    def _looks_like_code(self, text: str) -> bool:
        """
        Determina si un texto parece codigo (debe preservarse intacto).

        Args:
            text: Texto a verificar.

        Returns:
            True si parece codigo.
        """
        code_patterns = [
            r'\b(def|class|import|from|return|if __name__|async def)\b',
            r'^\s*(def |class |import |from |return |async )',
            r'[{}]\s*$',  # Termina con llave
            r'^\s*@\w+',  # Decorador
            r'^\s*\/\/',  # Comentario de codigo
            r'^\s*#include',  # C/C++
            r'^\s*(public|private|protected|static|void|int|str|bool)\s',
            r'function\s+\w+\s*\(',
        ]
        for pattern in code_patterns:
            if re.search(pattern, text, re.MULTILINE):
                return True
        return False

    @staticmethod
    def _line_is_only_stop_words(line: str) -> bool:
        """
        Verifica si una linea contiene solo stop words.

        Args:
            line: Linea de texto a verificar.

        Returns:
            True si todas las palabras son stop words.
        """
        if not line or not line.strip():
            return True
        words = line.strip().lower().split()
        if not words:
            return True
        # Eliminar signos de puntuacion
        clean_words = [w.strip(".,;:!?()[]{}\"'") for w in words]
        # Si hay al menos una palabra que no es stop word, la linea es util
        non_stop = [w for w in clean_words if w and w not in STOP_WORDS]
        return len(non_stop) == 0

    def _enforce_target_ratio(self, original: str, compressed: str, ratio: float) -> str:
        """
        Asegura que el texto comprimido cumpla con el ratio objetivo.

        Si el texto comprimido es mas largo de lo esperado, aplica
        truncado de lineas de baja prioridad para alcanzar el target.

        NOTA: Este metodo NO llama a extractive_compress() para evitar
        recursion infinita. Usa truncado directo de lineas.

        Args:
            original: Texto original (para referencia).
            compressed: Texto ya comprimido.
            ratio: Ratio objetivo.

        Returns:
            Texto que cumple (o se acerca) al ratio objetivo.
        """
        max_iterations = 3
        iteration = 0
        current = compressed
        target_tokens = max(1, int(self._count_tokens(original) * ratio))

        while iteration < max_iterations:
            current_tokens = self._count_tokens(current)
            if current_tokens <= target_tokens:
                break

            over_pct = current_tokens / max(target_tokens, 1)
            if over_pct <= 1.1:
                break  # Dentro del 10% de margen

            # Truncado directo: eliminar lineas cortas no criticas
            lines = current.split("\n")
            # Eliminar lineas vacias o muy cortas (< 3 chars)
            lines = [line for line in lines if len(line.strip()) > 3]
            # Si aun excede, eliminar lineas con solo stop words
            if self._count_tokens("\n".join(lines)) > target_tokens:
                critical_lines: list[str] = []
                for line in lines:
                    stripped = line.strip()
                    if self._has_preserved_keywords(stripped) or self._looks_like_code(stripped) or not self._line_is_only_stop_words(stripped):
                        critical_lines.append(line)
                # Asegurar que no quedamos vacios
                if len(critical_lines) >= len(lines) // 2:
                    lines = critical_lines
                else:
                    # Si perdimos demasiado, mantener al menos 50% de lineas
                    keep_count = max(len(critical_lines), len(lines) // 2)
                    # Mantener las mas largas (mas informacion)
                    sorted_lines = sorted(lines, key=len, reverse=True)
                    lines = sorted_lines[:keep_count]

            current = "\n".join(lines)
            iteration += 1

        # Si aun excede, truncar caracteres directamente
        if self._count_tokens(current) > target_tokens:
            max_chars = int(target_tokens * CHARS_PER_TOKEN)
            if len(current) > max_chars:
                # Truncar al final, pero no en medio de una palabra
                truncated = current[:max_chars]
                last_space = truncated.rfind(" ")
                if last_space > max_chars * 0.8:
                    truncated = truncated[:last_space]
                current = truncated + "..."

        return current
