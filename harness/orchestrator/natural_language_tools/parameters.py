"""NaturalLanguageTools parameters — mixin de extraccion de parametros.

Extraccion mecanica del modulo original
``harness/orchestrator/natural_language_tools.py`` (sin cambios de logica
ni firmas): extraccion de parametros estructurados desde texto.
"""

from __future__ import annotations

import re
from typing import Any

from harness.orchestrator.nlt_types import _PARAM_PATTERNS, NLTool


class _ParametersMixin:
    """Mixin con los metodos internos de extraccion de parametros."""

    def _extract_parameters(
        self,
        text: str,
        tool: NLTool,
    ) -> dict[str, Any]:
        """Extrae parametros estructurados desde el texto en lenguaje natural.

        Args:
            text: Texto del usuario en minusculas.
            tool: Herramienta objetivo.

        Returns:
            Diccionario con parametros extraidos.
        """
        params: dict[str, Any] = {}

        for param_name in tool.parameters:
            patterns = _PARAM_PATTERNS.get(param_name, [])
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    if value:
                        value = re.sub(r"\s+", " ", value).strip()
                        if param_name == "max":
                            try:
                                value = int(value)
                            except ValueError:
                                continue
                        params[param_name] = value
                        break

        return params
