"""NaturalLanguageTools parsing — mixin con la API publica de parseo.

Extraccion mecanica del modulo original
``harness/orchestrator/natural_language_tools.py`` (sin cambios de logica
ni firmas): parseo de lenguaje natural a tool call estructurada.
"""

from __future__ import annotations

import logging
from typing import Any

from harness.orchestrator.nlt_types import NLTResult

logger = logging.getLogger(__name__)


class _ParsingMixin:
    """Mixin con la API publica de parseo de lenguaje natural."""

    def parse(self, text: str) -> NLTResult | None:
        """Parsea texto en lenguaje natural a una llamada de herramienta.

        Ejecuta el pipeline completo: tokenizacion, semantic overlap
        scoring, seleccion de mejor candidato, y extraccion de
        parametros.

        Args:
            text: Texto en lenguaje natural del usuario.

        Returns:
            NLTResult si se encuentra una herramienta con confianza
            suficiente, None en caso contrario.

        Raises:
            ValueError: Si el texto esta vacio o es solo espacios.
        """
        if not text or not text.strip():
            raise ValueError("El texto de entrada no puede estar vacío")

        text_stripped = text.strip()

        # 1. Intentar encadenamiento si hay conectores
        if self._has_chain_connectors(text_stripped):
            chain_result = self._parse_chain(text_stripped)
            if chain_result and chain_result.confidence >= self._threshold:
                return chain_result

        # 2. Semantic overlap scoring contra todas las tools
        scores: list[tuple[str, float, dict[str, Any]]] = []
        for name, tool in self._tools.items():
            score, params = self._score_tool(text_stripped, tool)
            scores.append((name, score, params))

        # 3. Ordenar por confianza descendente
        scores.sort(key=lambda x: x[1], reverse=True)

        if not scores:
            return None

        best_name, best_score, best_params = scores[0]

        # 4. Construir structured_output
        structured = {
            "action": best_name,
            "parameters": best_params,
            "original_input": text_stripped,
        }

        # 5. Alternativas sobre el umbral
        alternatives = [
            (name, score)
            for name, score, _ in scores[1:]
            if score >= self._threshold
        ]

        logger.debug(
            "Parse: input='%s' -> tool='%s' confidence=%.3f alternatives=%d",
            text_stripped[:50], best_name, best_score, len(alternatives),
        )

        if best_score < self._threshold:
            logger.info(
                "Ninguna tool supera el umbral (mejor: '%s' con %.3f < %.2f)",
                best_name, best_score, self._threshold,
            )
            return None

        return NLTResult(
            tool=best_name,
            natural_input=text_stripped,
            structured_output=structured,
            confidence=best_score,
            alternatives=alternatives,
        )

    def parse_batch(
        self,
        texts: list[str],
    ) -> list[NLTResult | None]:
        """Parsea multiples textos en lote.

        Args:
            texts: Lista de textos en lenguaje natural.

        Returns:
            Lista de NLTResult (o None por cada texto sin match).
        """
        return [self.parse(t) for t in texts]
