"""NaturalLanguageTools registry — mixin de gestion de herramientas.

Extraccion mecanica del modulo original
``harness/orchestrator/natural_language_tools.py`` (sin cambios de logica
ni firmas): registro, eliminacion, consulta y umbral de confianza.
"""

from __future__ import annotations

import logging

from harness.orchestrator.nlt_types import NLTool

logger = logging.getLogger(__name__)


class _RegistryMixin:
    """Mixin con la API publica de gestion de herramientas."""

    def register_tool(self, tool: NLTool) -> None:
        """Registra una nueva herramienta en el toolkit.

        Args:
            tool: Instancia de NLTool a registrar. Si ya existe una
                herramienta con el mismo nombre, se sobrescribe.

        Raises:
            TypeError: Si tool no es una instancia de NLTool.
            ValueError: Si el nombre de la herramienta esta vacio.
        """
        if not isinstance(tool, NLTool):
            raise TypeError(
                f"Se esperaba NLTool, se recibio {type(tool).__name__}"
            )
        if not tool.name or not tool.name.strip():
            raise ValueError("El nombre de la herramienta no puede estar vacío")
        self._tools[tool.name] = tool
        logger.info(
            "Tool registrada: '%s' (descripcion: %s)",
            tool.name, tool.description[:60],
        )

    def unregister_tool(self, name: str) -> bool:
        """Elimina una herramienta registrada.

        Args:
            name: Nombre de la herramienta a eliminar.

        Returns:
            True si fue eliminada, False si no existia.
        """
        if name in self._tools:
            del self._tools[name]
            logger.info("Tool eliminada: '%s'", name)
            return True
        logger.warning("Intento de eliminar tool inexistente: '%s'", name)
        return False

    def get_tool(self, name: str) -> NLTool | None:
        """Obtiene una herramienta por su nombre.

        Args:
            name: Nombre de la herramienta.

        Returns:
            NLTool si existe, None en caso contrario.
        """
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """Lista los nombres de todas las herramientas registradas.

        Returns:
            Lista ordenada alfabeticamente de nombres de herramientas.
        """
        return sorted(self._tools.keys())

    def get_tool_count(self) -> int:
        """Retorna el numero de herramientas registradas.

        Returns:
            Cantidad de herramientas en el toolkit.
        """
        return len(self._tools)

    def set_confidence_threshold(self, threshold: float) -> None:
        """Ajusta el umbral de confianza para el matching.

        Args:
            threshold: Nuevo umbral entre 0.0 y 1.0.

        Raises:
            ValueError: Si el umbral esta fuera del rango [0.0, 1.0].
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                f"El umbral debe estar entre 0.0 y 1.0, se recibio {threshold}"
            )
        self._threshold = threshold
        logger.info("Umbral de confianza ajustado a %.2f", threshold)
