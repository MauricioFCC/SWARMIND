"""Tool Registry — Auto-discovery via import-time registration.

Incluye el patron de ciclo de vida inspirado en deepseek-harness (Cordis):
on_load/on_unload en PluginBase y suscripcion automatica al EventBus
durante load_all cuando el plugin declara events().
"""
from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PluginBase:
    """Base class for all plugins."""

    name: str = ""
    description: str = ""
    version: str = "0.1.0"

    def execute(self, **kwargs) -> Any:
        raise NotImplementedError

    def on_load(self, ctx: Any) -> None:
        """Hook de ciclo de vida invocado al cargar el plugin.

        Args:
            ctx: Contexto compartido (EventBus, config, etc.). Puede ser None.

        Returns:
            None. No-op por defecto para compatibilidad con plugins existentes.
        """
        return

    def on_unload(self, ctx: Any) -> None:
        """Hook de ciclo de vida invocado al descargar el plugin.

        Args:
            ctx: Contexto compartido. Puede ser None.

        Returns:
            None. No-op por defecto para compatibilidad con plugins existentes.
        """
        return

    def events(self) -> tuple[str, ...]:
        """Eventos del EventBus a los que el plugin desea suscribirse.

        Returns:
            Tupla de nombres de evento (p. ej. ("tool/run",)). Default ().
        """
        return ()


class ToolRegistry:
    """Central tool registry with auto-discovery y ciclo de vida de plugins.

    Args:
        event_bus: EventBus inyectado (DIP). Si es None, load_all() solo
            invoca on_load sin suscribir eventos (no falla).
    """

    def __init__(self, event_bus: Any | None = None) -> None:
        """Inicializa el registry.

        Args:
            event_bus: EventBus para suscripcion automatica de plugins.
        """
        self._tools: dict[str, type[PluginBase]] = {}
        self._instances: dict[str, PluginBase] = {}
        self._discovered: bool = False
        self._event_bus: Any | None = event_bus
        self._subscriptions: dict[str, dict[str, str]] = {}
        self._loaded: dict[str, PluginBase] = {}
        self._known_events: set[str] = set()

    def register(self, name: str | None = None) -> Callable:
        """Decorator to register a tool."""
        def decorator(cls: type[PluginBase]) -> type[PluginBase]:
            n = name or cls.__name__
            self._tools[n] = cls
            logger.debug("Registered: %s", n)
            return cls
        return decorator

    def get(self, name: str) -> PluginBase | None:
        """Get a tool instance by name."""
        if not self._discovered:
            self.discover_all()
        if name in self._instances:
            return self._instances[name]
        cls = self._tools.get(name)
        if cls is None:
            return None
        inst = cls()
        self._instances[name] = inst
        return inst

    def discover_all(self, path: str | None = None) -> int:
        """Auto-discover tools by importing all .py files."""
        if self._discovered:
            return len(self._tools)
        if path is None:
            path = str(Path(__file__).resolve().parent / "tools")
        p = Path(path)
        if not p.exists():
            self._discovered = True
            return 0
        count = 0
        for py_file in sorted(p.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"harness.plugins.tools.{py_file.stem}", py_file
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    count += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed: %s: %s", py_file.name, exc)
        self._discovered = True
        logger.info("Discovered %d tools", count)
        return count

    def load_all(self, ctx: Any = None) -> int:
        """Instancia y activa todos los plugins descubiertos.

        Carga cada plugin: reutiliza/cachea la instancia, invoca on_load(ctx)
        y, si hay EventBus inyectado y el plugin declara events(), lo suscribe
        automaticamente. Idempotente: plugins ya cargados no se recargan.

        Args:
            ctx: Contexto compartido para on_load. Puede ser None.

        Returns:
            Numero de plugins cargados en esta llamada.
        """
        if not self._discovered:
            self.discover_all()
        count = 0
        for name, cls in self._tools.items():
            if name in self._loaded:
                continue
            inst = self._instances.get(name)
            if inst is None:
                inst = cls()
                self._instances[name] = inst
            load_hook = getattr(inst, "on_load", None)
            if load_hook is not None:
                load_hook(ctx)
            self._subscribe_plugin(inst, ctx)
            self._loaded[name] = inst
            logger.debug("Loaded plugin: %s", name)
            count += 1
        return count

    def unload_all(self, ctx: Any = None) -> int:
        """Descarga todos los plugins vivos.

        Para cada plugin cargado: desuscribe del EventBus e invoca
        on_unload(ctx). Idempotente: una segunda llamada retorna 0.

        Args:
            ctx: Contexto compartido para on_unload. Puede ser None.

        Returns:
            Numero de plugins descargados en esta llamada.
        """
        count = 0
        for name, inst in list(self._loaded.items()):
            self._unsubscribe_plugin(inst, ctx)
            unload_hook = getattr(inst, "on_unload", None)
            if unload_hook is not None:
                unload_hook(ctx)
            del self._loaded[name]
            logger.debug("Unloaded plugin: %s", name)
            count += 1
        return count

    def _subscribe_plugin(self, plugin: PluginBase, ctx: Any) -> None:
        """Suscribe el plugin al EventBus segun su declaracion events().

        Args:
            plugin: Instancia del plugin a suscribir.
            ctx: Contexto compartido (el bus vive en self._event_bus).
        """
        bus = self._event_bus
        if bus is None:
            return
        name = getattr(plugin, "name", "") or type(plugin).__name__
        declared = getattr(plugin, "events", lambda: ())()
        if not declared:
            return
        subs = self._subscriptions.setdefault(name, {})
        for event_name in declared:
            handler_name = f"on_{event_name.replace('/', '_')}"
            handler = getattr(plugin, handler_name, None)
            if handler is None:
                logger.debug(
                    "Plugin %s declara evento %s sin handler %s; ignorado",
                    name, event_name, handler_name,
                )
                continue
            if event_name not in self._known_events:
                self._known_events.add(event_name)
                logger.info("Registrando evento nuevo '%s' para plugin %s", event_name, name)
            sub_id = bus.subscribe(event_name, partial(handler))
            subs[event_name] = sub_id
            logger.debug("Plugin %s suscrito a %s (%s)", name, event_name, sub_id)

    def _unsubscribe_plugin(self, plugin: PluginBase, ctx: Any) -> None:
        """Desuscribe el plugin del EventBus.

        Args:
            plugin: Instancia del plugin a desuscribir.
            ctx: Contexto compartido (el bus vive en self._event_bus).
        """
        bus = self._event_bus
        name = getattr(plugin, "name", "") or type(plugin).__name__
        subs = self._subscriptions.get(name)
        if subs is None:
            return
        if bus is not None:
            for event_name, sub_id in subs.items():
                bus.unsubscribe(sub_id)
                logger.debug("Plugin %s desuscrito de %s", name, event_name)
        subs.clear()

    def list_tools(self) -> list[dict[str, Any]]:
        if not self._discovered:
            self.discover_all()
        return sorted(
            [{"name": n, "description": getattr(c, "description", ""), "class": c.__name__}
             for n, c in self._tools.items()],
            key=lambda t: t["name"],
        )

    def get_stats(self) -> dict[str, Any]:
        return {
            "total": len(self._tools),
            "discovered": self._discovered,
            "loaded": len(self._loaded),
            "tools": self.list_tools(),
        }


registry = ToolRegistry()
