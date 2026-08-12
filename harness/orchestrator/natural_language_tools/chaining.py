"""NaturalLanguageTools chaining — mixin de encadenamiento de tools.

Extraccion mecanica del modulo original
``harness/orchestrator/natural_language_tools.py`` (sin cambios de logica
ni firmas): deteccion de conectores, parseo de cadenas y division
por conectores.
"""

from __future__ import annotations

from typing import Any

from harness.orchestrator.nlt_types import _CHAIN_CONNECTORS, NLTResult


class _ChainingMixin:
    """Mixin con los metodos internos de encadenamiento de herramientas."""

    def _has_chain_connectors(self, text: str) -> bool:
        """Verifica si el texto contiene conectores de encadenamiento validos.

        Args:
            text: Texto a evaluar.

        Returns:
            True si se detecta encadenamiento valido.
        """
        segments = self._split_by_connectors(text)
        if len(segments) < 2:
            return False

        match_count = 0
        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            scores = []
            for name, tool in self._tools.items():
                score, _ = self._score_tool(seg, tool)
                scores.append((name, score))
            scores.sort(key=lambda x: x[1], reverse=True)
            if scores and scores[0][1] >= self._threshold:
                match_count += 1
                if match_count >= 2:
                    return True
        return False

    def _parse_chain(self, text: str) -> NLTResult | None:
        """Parsea un texto con multiples intenciones encadenadas.

        Args:
            text: Texto con conectores de encadenamiento.

        Returns:
            NLTResult con el primer match y el resto encadenado,
            o None si ningun segmento supera el umbral.
        """
        segments = self._split_by_connectors(text)

        if not segments:
            return None

        chain_results: list[NLTResult] = []
        first_result: NLTResult | None = None

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue

            result = self._parse_single(segment)
            if result is None:
                continue

            if first_result is None:
                first_result = result
            else:
                chain_results.append(result)

        if first_result is None:
            return None

        first_result.chain = chain_results
        if chain_results:
            first_result.confidence = min(
                1.0, first_result.confidence + 0.05,
            )

        return first_result

    def _parse_single(self, text: str) -> NLTResult | None:
        """Parsea un segmento individual de texto (sin encadenamiento).

        Args:
            text: Segmento de texto.

        Returns:
            NLTResult o None si no hay match suficiente.
        """
        scores: list[tuple[str, float, dict[str, Any]]] = []

        for name, tool in self._tools.items():
            score, params = self._score_tool(text, tool)
            scores.append((name, score, params))

        scores.sort(key=lambda x: x[1], reverse=True)

        if not scores or scores[0][1] < self._threshold:
            return None

        best_name, best_score, best_params = scores[0]

        alternatives = [
            (name, score)
            for name, score, _ in scores[1:]
            if score >= self._threshold
        ]

        return NLTResult(
            tool=best_name,
            natural_input=text,
            structured_output={
                "action": best_name,
                "parameters": best_params,
                "original_input": text,
            },
            confidence=best_score,
            alternatives=alternatives,
        )

    @staticmethod
    def _split_by_connectors(text: str) -> list[str]:
        """Divide un texto por conectores de encadenamiento.

        Args:
            text: Texto completo.

        Returns:
            Lista de segmentos.
        """
        text_lower = text.lower()
        split_points = []
        for connector in _CHAIN_CONNECTORS:
            conn_clean = connector.strip()
            start = 0
            while True:
                pos = text_lower.find(connector, start)
                if pos == -1:
                    break
                split_points.append((pos, len(connector.strip()), conn_clean))
                start = pos + 1

        if not split_points:
            return [text]

        split_points.sort(key=lambda x: x[0])

        segments: list[str] = []
        last_end = 0
        for pos, length, _ in split_points:
            if pos > last_end:
                segment = text[last_end:pos].strip()
                if segment:
                    segments.append(segment)
                last_end = pos + length + 1

        remainder = text[last_end:].strip()
        if remainder:
            segments.append(remainder)

        return segments
