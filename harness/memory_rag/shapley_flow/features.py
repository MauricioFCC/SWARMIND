"""Mixin de extraccion de caracteristicas para ``ShapleyFlow``.

Extraido mecanicamente de ``shapley_flow.py`` (regla AGR < 500 lineas).
Contiene ``_extract_features``, que convierte cada seccion del prompt
en metricas numericas para el modelo de valor.
"""
from __future__ import annotations

from .models import _SectionFeatures


class _FeatureExtractionMixin:
    """Extraccion de caracteristicas de secciones para el modelo de valor."""

    def _extract_features(
        self,
        sections: dict[str, str],
        section_names: list[str],
    ) -> list[_SectionFeatures]:
        """Extrae caracteristicas de cada seccion para el modelo de valor.

        Args:
            sections: Diccionario original de secciones.
            section_names: Lista ordenada de nombres de seccion.

        Returns:
            Lista de ``_SectionFeatures`` con las metricas extraidas.
        """
        features: list[_SectionFeatures] = []
        for idx, name in enumerate(section_names):
            text = sections[name]
            # Estimacion simple de tokens: ~4 chars por token
            token_count = max(1, len(text) // 4)

            # Densidad semantica: proporcion de palabras unicas
            words = text.lower().split()
            unique_ratio = len(set(words)) / max(len(words), 1)
            semantic_density = min(
                self._default_semantic_density + unique_ratio * 0.5,
                1.0,
            )

            # Relevancia por keywords tecnicas
            tech_keywords = {
                "implement", "function", "class", "def", "import",
                "algorithm", "api", "endpoint", "database", "query",
                "test", "async", "await", "error", "exception",
                "optimize", "refactor", "deploy", "config",
            }
            keyword_matches = sum(1 for w in words if w in tech_keywords)
            keyword_relevance = min(keyword_matches / max(len(words), 1) * 5, 1.0)

            # Deteccion de codigo
            has_code = "```" in text or "def " in text or "class " in text

            features.append(_SectionFeatures(
                name=name,
                text=text,
                token_count=token_count,
                semantic_density=round(semantic_density, 4),
                position_index=idx,
                keyword_relevance=round(keyword_relevance, 4),
                has_code=has_code,
            ))

        return features
