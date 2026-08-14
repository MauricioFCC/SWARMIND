"""NaturalLanguageTools utils — mixin con utilidades de consulta.

Extraccion mecanica del modulo original
``harness/orchestrator/natural_language_tools.py`` (sin cambios de logica
ni firmas): sugerencias de tools, busqueda por descripcion y match exacto.
"""

from __future__ import annotations


class _UtilsMixin:
    """Mixin con la API publica de utilidades."""

    def suggest_tools(
        self,
        text: str,
        top_n: int = 3,
    ) -> list[tuple[str, float]]:
        """Sugiere las mejores herramientas para un texto sin filtrar por umbral.

        Args:
            text: Texto en lenguaje natural.
            top_n: Numero maximo de sugerencias a retornar.

        Returns:
            Lista de (tool_name, confidence) ordenada por confianza
            descendente.
        """
        if not text or not text.strip():
            return []

        text_stripped = text.strip()
        scores: list[tuple[str, float]] = []

        for name, tool in self._tools.items():
            score, _ = self._score_tool(text_stripped, tool)
            scores.append((name, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_n]

    def find_tools_by_description(
        self,
        keyword: str,
    ) -> list[str]:
        """Busca herramientas cuya descripcion contenga una palabra clave.

        Args:
            keyword: Palabra clave a buscar en nombres y descripciones.

        Returns:
            Lista de nombres de herramientas que coinciden.
        """
        keyword_lower = keyword.lower()
        results: list[str] = []
        for name, tool in self._tools.items():
            if keyword_lower in name.lower() or keyword_lower in tool.description.lower():
                results.append(name)
            else:
                for ex in tool.examples:
                    if keyword_lower in ex.lower():
                        results.append(name)
                        break
        return results

    def match_exact(self, text: str) -> str | None:
        """Verifica si el texto coincide exactamente con el nombre de una tool.

        Args:
            text: Texto a verificar.

        Returns:
            Nombre de la tool si hay match exacto, None en caso contrario.
        """
        text_lower = text.strip().lower()
        for name in self._tools:
            if name.lower() == text_lower:
                return name
        return None
