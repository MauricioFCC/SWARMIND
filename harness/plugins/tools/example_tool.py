"""Example tools demonstrating the plugin pattern.

GreeterTool muestra el ciclo de vida completo (on_load/on_unload/events +
handler on_tool_loaded). EchoTool usa los defaults no-op de PluginBase
para demostrar que los plugins existentes siguen funcionando sin cambios.
"""
import logging
from typing import Any

from harness.plugins.registry import PluginBase, registry

logger = logging.getLogger(__name__)


@registry.register("greeter")
class GreeterTool(PluginBase):
    """Plugin de ejemplo con ciclo de vida Cordis (load/unload/events)."""
    name = "greeter"
    description = "Saluda al usuario"

    def execute(self, name: str = "Mundo", **kwargs) -> str:
        return f"Hola {name}!"

    def on_load(self, ctx: Any) -> None:
        """Hook de carga: notifica la activacion del plugin.

        Args:
            ctx: Contexto compartido (EventBus/config). Puede ser None.
        """
        logger.info("[greeter] cargado (ctx=%s)", "provisto" if ctx is not None else "ninguno")

    def on_unload(self, ctx: Any) -> None:
        """Hook de descarga: notifica la desactivacion del plugin.

        Args:
            ctx: Contexto compartido. Puede ser None.
        """
        logger.info("[greeter] descargado")

    def events(self) -> tuple[str, ...]:
        """Eventos a los que suscribirse (se activa con tool/loaded).

        Returns:
            Tupla con el evento "tool/loaded".
        """
        return ("tool/loaded",)

    def on_tool_loaded(self, event: Any) -> None:
        """Handler del evento tool/loaded: notifica la llegada del evento.

        Args:
            event: Evento del bus (harness.orchestrator.event_bus.Event).
        """
        logger.info("[greeter] evento tool/loaded recibido: %s", event.channel)


@registry.register("echo")
class EchoTool(PluginBase):
    """Plugin sin hooks de ciclo de vida: usa defaults no-op de PluginBase."""
    name = "echo"
    description = "Repite el texto"

    def execute(self, text: str = "", **kwargs) -> str:
        return text