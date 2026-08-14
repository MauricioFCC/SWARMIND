"""NaturalLanguageTools scoring — mixin con scoring semantico.

Extraccion mecanica del modulo original
``harness/orchestrator/natural_language_tools.py`` (sin cambios de logica
ni firmas): stemming, tokenizacion, token overlap y score de confianza.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from harness.orchestrator.nlt_types import _STOPWORDS, NLTool


class _ScoringMixin:
    """Mixin con los metodos internos de scoring semantico."""

    @staticmethod
    def _stem(word: str) -> str:
        """Reduce una palabra a su raiz (stemming simple espanol/ingles).

        Aplica reglas de stemming para verbos y nombres espanoles,
        eliminando sufijos de infinitivo, conjugaciones y derivaciones
        nominales comunes.

        Args:
            word: Palabra en minusculas.

        Returns:
            Raiz estimada de la palabra.
        """
        if len(word) < 5:
            return word

        for suffix in ("ar", "er", "ir"):
            if word.endswith(suffix) and len(word) > 4:
                return word[:-2]

        for suffix in (
            "ando", "iendo", "ando",
            "asteis", "isteis", "abais",
            "aron", "eron", "aban", "asen",
            "aria", "eria", "iria",
            "arias", "erias", "irias",
            "iamos", "erais",
            "aste", "iste",
            "aba", "ada", "ado", "ido",
            "ian", "ias",
        ):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                return word[:-len(suffix)]

        if word.endswith("cion") and len(word) > 6:
            return word[:-4]
        if word.endswith("miento") and len(word) > 8:
            return word[:-6]
        if word.endswith("encia") and len(word) > 6:
            return word[:-5]

        return word

    def _score_tool(
        self,
        text: str,
        tool: NLTool,
    ) -> tuple[float, dict[str, Any]]:
        """Calcula la confianza del matching entre texto y herramienta.

        Combina multiples senales con pesos adaptativos:
          - Overlap de tokens con el nombre de la tool (peso 0.15)
          - Stem match del nombre contra tokens de entrada (peso 0.20)
          - Substring detection del nombre en el texto (peso 0.10)
          - Overlap de tokens con descripcion (peso 0.20)
          - Overlap con ejemplos (peso 0.20)
          - Fuzzy matching de stems (peso 0.15)

        Args:
            text: Texto del usuario normalizado.
            tool: Herramienta a evaluar.

        Returns:
            Tupla (confianza, parametros_extraidos).
        """
        text_lower = text.lower()
        tokens_input = self._tokenize(text_lower)

        if not tokens_input:
            return 0.0, {}

        name_lower = tool.name.lower()
        name_tokens = self._tokenize(name_lower)
        name_stem = self._stem(name_lower)
        stems_input = {self._stem(t) for t in tokens_input}

        score = 0.0

        # Senal 1: Overlap de tokens con nombre (peso 0.15)
        name_overlap = self._token_overlap(tokens_input, name_tokens)
        score += 0.15 * name_overlap

        # Senal 2: Stem match
        stem_matched = any(
            t.startswith(name_stem) for t in tokens_input
        ) or any(
            name_stem.startswith(t) for t in stems_input
        )
        if stem_matched:
            score += 0.20

        # Senal 3: Substring detection (peso 0.10)
        if name_lower in text_lower or (len(name_stem) > 3 and name_stem in text_lower):
            score += 0.10

        # Senal 4: Overlap con descripcion (peso 0.20)
        desc_tokens = self._tokenize(tool.description.lower())
        desc_overlap = self._token_overlap(tokens_input, desc_tokens)
        score += 0.20 * desc_overlap

        # Senal 5: Overlap con ejemplos (peso 0.20)
        example_score = 0.0
        if tool.examples:
            best_example_overlap = 0.0
            for example in tool.examples:
                ex_tokens = self._tokenize(example.lower())
                overlap = self._token_overlap(tokens_input, ex_tokens)
                best_example_overlap = max(best_example_overlap, overlap)
            example_score = best_example_overlap
        score += 0.20 * example_score

        # Senal 6: Fuzzy match sobre stems (peso 0.15)
        input_stem_text = " ".join(sorted(stems_input))
        name_stem_text = name_stem if name_stem else name_lower
        fuzzy_stem = SequenceMatcher(None, name_stem_text, input_stem_text).ratio()
        score += 0.15 * fuzzy_stem

        params = self._extract_parameters(text_lower, tool)

        return min(score, 1.0), params

    def _token_overlap(
        self,
        tokens_a: set[str],
        tokens_b: set[str],
    ) -> float:
        """Calcula el Jaccard overlap entre dos conjuntos de tokens.

        Args:
            tokens_a: Primer conjunto de tokens.
            tokens_b: Segundo conjunto de tokens.

        Returns:
            Coeficiente de Jaccard (0.0 a 1.0).
        """
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b
        return len(intersection) / len(union)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Tokeniza y normaliza un texto, removiendo stopwords.

        Args:
            text: Texto a tokenizar.

        Returns:
            Conjunto de tokens significativos (sin stopwords).
        """
        tokens = re.findall(r"[a-záéíóúüñ]+", text.lower())
        return {
            t for t in tokens
            if t not in _STOPWORDS and len(t) > 1
        }
