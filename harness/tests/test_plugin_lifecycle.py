"""Tests del ciclo de vida de plugins (patron Cordis: on_load/on_unload/events).

Cubre: hooks default no-op, load_all, unload_all idempotente, suscripcion
automatica al EventBus, compatibilidad total con la API existente
(get/register/discover_all/list_tools/get_stats) y robustez ante clases
que no heredan PluginBase.
"""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from harness.orchestrator.event_bus import Event, EventBus, EventPriority
from harness.plugins.registry import PluginBase, ToolRegistry
from harness.plugins.tools.example_tool import GreeterTool

# ===========================================================================
# Plugins de prueba
# ===========================================================================


class LoadSpyPlugin(PluginBase):
    """Plugin que registra invocaciones de on_load/on_unload."""

    name = "load_spy"
    description = "Espia el ciclo de vida"

    def __init__(self) -> None:
        """Inicializa los espias por instancia (sin estado de clase compartido)."""
        super().__init__()
        self.loads: list[Any] = []
        self.unloads: list[Any] = []

    def execute(self, **kwargs: Any) -> str:
        return "spy"

    def on_load(self, ctx: Any) -> None:
        self.loads.append(ctx)

    def on_unload(self, ctx: Any) -> None:
        self.unloads.append(ctx)


class EventConsumerPlugin(PluginBase):
    """Plugin que se suscribe al evento tool/run con handler on_tool_run."""

    name = "event_consumer"
    description = "Consume eventos tool/run"

    def __init__(self) -> None:
        """Inicializa el espia por instancia (sin estado de clase compartido)."""
        super().__init__()
        self.received: list[Event] = []

    def execute(self, **kwargs: Any) -> str:
        return "consumer"

    def events(self) -> tuple[str, ...]:
        return ("tool/run",)

    def on_tool_run(self, event: Event) -> None:
        self.received.append(event)


class NoHandlerPlugin(PluginBase):
    """Plugin que declara un evento sin handler correspondiente."""
    name = "no_handler"
    description = "Declara evento sin handler"

    def execute(self, **kwargs: Any) -> str:
        return "nohandler"

    def events(self) -> tuple[str, ...]:
        return ("tool/missing",)


class PlainClassPlugin:
    """Clase registrada que NO hereda PluginBase (robustez)."""
    name = "plain"
    description = "Sin herencia"

    def execute(self, **kwargs: Any) -> str:
        return "plain"


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def event_bus() -> EventBus:
    """EventBus real aislado por test."""
    return EventBus(max_queue=100)


@pytest.fixture
def registry(event_bus: EventBus) -> ToolRegistry:
    """ToolRegistry con EventBus inyectado (DI)."""
    reg = ToolRegistry(event_bus=event_bus)
    reg._discovered = True  # evitar auto-discovery en tests
    return reg


def _make_event(channel: str = "tool/run", **data: Any) -> Event:
    """Construye un Event valido para publish."""
    import time
    return Event(
        event_id="evt-test",
        channel=channel,
        data=data,
        source="test",
        priority=EventPriority.NORMAL,
        timestamp=time.time(),
    )


def _spy(registry: ToolRegistry, name: str, plugin_cls: type[PluginBase]) -> PluginBase:
    """Devuelve la instancia del plugin espia registrada en el registry.

    Registra la clase en ``_tools`` y la instancia en ``_instances`` para
    que ``load_all`` la reutilice (evita estado de clase compartido).

    Args:
        registry: ToolRegistry de prueba.
        name: Nombre de registro del plugin.
        plugin_cls: Clase del plugin espia.

    Returns:
        Instancia del plugin, cacheada en ``registry._instances``.
    """
    registry._tools[name] = plugin_cls
    inst = registry._instances.get(name)
    if inst is None:
        inst = plugin_cls()
        registry._instances[name] = inst
    return inst


# ===========================================================================
# PluginBase: hooks default no-op
# ===========================================================================


class TestPluginBaseLifecycle:
    """Tests de los hooks de ciclo de vida con default no-op."""

    def test_on_load_default_noop(self) -> None:
        """on_load default no lanza y retorna None."""
        plugin = PluginBase()
        assert plugin.on_load(None) is None

    def test_on_unload_default_noop(self) -> None:
        """on_unload default no lanza y retorna None."""
        plugin = PluginBase()
        assert plugin.on_unload(None) is None

    def test_events_default_empty(self) -> None:
        """events default retorna tupla vacia."""
        plugin = PluginBase()
        assert plugin.events() == ()

    def test_hooks_not_abstract(self) -> None:
        """Un plugin minimo (solo execute) puede instanciarse y cargarse."""
        class MinimalPlugin(PluginBase):
            name = "minimal"
            def execute(self, **kwargs: Any) -> str:
                return "min"

        inst = MinimalPlugin()
        assert inst.on_load(None) is None
        assert inst.on_unload(None) is None
        assert inst.events() == ()


# ===========================================================================
# load_all
# ===========================================================================


class TestLoadAll:
    """Tests de load_all."""

    def test_load_all_calls_on_load(self, registry: ToolRegistry) -> None:
        """load_all invoca on_load(ctx) para cada plugin."""
        spy = _spy(registry, "spy", LoadSpyPlugin)
        spy.loads.clear()
        count = registry.load_all(ctx="ctx-1")
        assert count == 1
        assert spy.loads == ["ctx-1"]

    def test_load_all_returns_count(self, registry: ToolRegistry) -> None:
        """load_all retorna el numero de plugins cargados."""
        registry._tools["a"] = LoadSpyPlugin
        registry._tools["b"] = LoadSpyPlugin
        assert registry.load_all(ctx=None) == 2

    def test_load_all_idempotent(self, registry: ToolRegistry) -> None:
        """Segunda llamada a load_all no recarga ni re-invoca on_load."""
        spy = _spy(registry, "spy", LoadSpyPlugin)
        spy.loads.clear()
        first = registry.load_all(ctx=None)
        second = registry.load_all(ctx=None)
        assert first == 1
        assert second == 0
        assert len(spy.loads) == 1

    def test_load_all_without_event_bus(self) -> None:
        """load_all sin EventBus inyectado no falla y no suscribe."""
        reg = ToolRegistry(event_bus=None)
        reg._discovered = True
        reg._tools["consumer"] = EventConsumerPlugin
        count = reg.load_all(ctx=None)
        assert count == 1
        assert reg._subscriptions == {}

    def test_load_all_calls_discover_if_needed(self) -> None:
        """load_all dispara discover_all si aun no se descubrio."""
        reg = ToolRegistry()
        with mock.patch.object(reg, "discover_all", return_value=0) as mocked:
            reg.load_all(ctx=None)
            mocked.assert_called_once()

    def test_load_all_reuses_get_instance(self, registry: ToolRegistry) -> None:
        """load_all reutiliza la instancia cacheada por get()."""
        registry._tools["spy"] = LoadSpyPlugin
        via_get = registry.get("spy")
        registry.load_all(ctx=None)
        assert registry._instances["spy"] is via_get
        assert registry._loaded["spy"] is via_get

    def test_load_all_with_non_plugin_class(self, registry: ToolRegistry) -> None:
        """load_all tolera clases que no heredan PluginBase (getattr defensivo)."""
        registry._tools["plain"] = PlainClassPlugin
        count = registry.load_all(ctx=None)
        assert count == 1


# ===========================================================================
# Suscripcion automatica al EventBus
# ===========================================================================


class TestAutoSubscribe:
    """Tests de suscripcion automatica via events()/on_<evento>."""

    def test_subscribe_on_load(self, registry: ToolRegistry, event_bus: EventBus) -> None:
        """Plugin con events() y handler se suscribe al EventBus."""
        registry._tools["consumer"] = EventConsumerPlugin
        registry.load_all(ctx=None)
        assert "event_consumer" in registry._subscriptions
        assert "tool/run" in registry._subscriptions["event_consumer"]

    def test_handler_receives_event(self, registry: ToolRegistry, event_bus: EventBus) -> None:
        """Publicar tool/run entrega el evento al handler del plugin."""
        consumer = _spy(registry, "consumer", EventConsumerPlugin)
        consumer.received.clear()
        registry.load_all(ctx=None)
        event = _make_event(channel="tool/run", task="x")
        event_bus.publish(event)
        assert consumer.received == [event]

    def test_new_event_channel_registered(self, registry: ToolRegistry, event_bus: EventBus) -> None:
        """Suscribirse a un canal nuevo no falla (EventBus implicito)."""
        registry._tools["consumer"] = EventConsumerPlugin
        registry.load_all(ctx=None)
        assert "tool/run" in registry._known_events

    def test_event_without_handler_is_ignored(self, registry: ToolRegistry, event_bus: EventBus) -> None:
        """Evento declarado sin handler no rompe la carga."""
        registry._tools["nohandler"] = NoHandlerPlugin
        count = registry.load_all(ctx=None)
        assert count == 1
        # No debe haber suscripcion activa para tool/missing
        assert all("tool/missing" not in subs for subs in registry._subscriptions.values())

    def test_unsubscribe_on_unload(self, registry: ToolRegistry, event_bus: EventBus) -> None:
        """Tras unload_all el handler ya no recibe eventos."""
        consumer = _spy(registry, "consumer", EventConsumerPlugin)
        consumer.received.clear()
        registry.load_all(ctx=None)
        registry.unload_all(ctx=None)
        event_bus.publish(_make_event(channel="tool/run"))
        assert consumer.received == []


# ===========================================================================
# unload_all
# ===========================================================================


class TestUnloadAll:
    """Tests de unload_all."""

    def test_unload_all_calls_on_unload(self, registry: ToolRegistry) -> None:
        """unload_all invoca on_unload(ctx) por plugin cargado."""
        spy = _spy(registry, "spy", LoadSpyPlugin)
        spy.unloads.clear()
        registry.load_all(ctx="load")
        count = registry.unload_all(ctx="unload")
        assert count == 1
        assert spy.unloads == ["unload"]

    def test_unload_all_idempotent(self, registry: ToolRegistry) -> None:
        """Segunda llamada a unload_all retorna 0 sin romper."""
        registry._tools["spy"] = LoadSpyPlugin
        registry.load_all(ctx=None)
        first = registry.unload_all(ctx=None)
        second = registry.unload_all(ctx=None)
        assert first == 1
        assert second == 0

    def test_unload_all_clears_loaded(self, registry: ToolRegistry) -> None:
        """Tras unload_all, _loaded queda vacio."""
        registry._tools["spy"] = LoadSpyPlugin
        registry.load_all(ctx=None)
        registry.unload_all(ctx=None)
        assert registry._loaded == {}

    def test_reload_after_unload(self, registry: ToolRegistry) -> None:
        """Cargar, descargar y recargar funciona (ciclo completo)."""
        spy = _spy(registry, "spy", LoadSpyPlugin)
        spy.loads.clear()
        spy.unloads.clear()
        assert registry.load_all(ctx="c1") == 1
        assert registry.unload_all(ctx="c2") == 1
        assert registry.load_all(ctx="c3") == 1
        assert spy.loads == ["c1", "c3"]
        assert spy.unloads == ["c2"]


# ===========================================================================
# Compatibilidad con la API existente
# ===========================================================================


class TestCompatibility:
    """Compatibilidad total tras anadir el ciclo de vida."""

    def test_get_still_works(self, registry: ToolRegistry) -> None:
        """get() sigue funcionando igual tras load/unload."""
        registry._tools["consumer"] = EventConsumerPlugin
        registry.load_all(ctx=None)
        inst = registry.get("consumer")
        assert isinstance(inst, EventConsumerPlugin)
        assert inst.execute() == "consumer"

    def test_list_tools_still_works(self, registry: ToolRegistry) -> None:
        """list_tools sigue listando plugins."""
        registry._tools["load_spy"] = LoadSpyPlugin
        registry.load_all(ctx=None)
        names = [t["name"] for t in registry.list_tools()]
        assert names == ["load_spy"]

    def test_get_stats_includes_loaded(self, registry: ToolRegistry) -> None:
        """get_stats expone contador de plugins cargados."""
        registry._tools["spy"] = LoadSpyPlugin
        registry.load_all(ctx=None)
        stats = registry.get_stats()
        assert stats["loaded"] == 1
        registry.unload_all(ctx=None)
        assert registry.get_stats()["loaded"] == 0

    def test_greeter_example_has_lifecycle(self) -> None:
        """GreeterTool demuestra on_load/on_unload/events."""
        tool = GreeterTool()
        assert tool.on_load(None) is None
        assert tool.on_unload(None) is None
        assert "tool/loaded" in tool.events()
        assert callable(getattr(tool, "on_tool_loaded", None))

    def test_global_registry_load_all_smoke(self) -> None:
        """Smoke: load_all/unload_all sobre el singleton global sin bus."""
        from harness.plugins.registry import registry as global_registry

        global_registry._discovered = False
        try:
            n = global_registry.load_all(None)
            assert n >= 1  # greeter + echo descubiertos
            assert global_registry.unload_all(None) == n
        finally:
            global_registry._loaded.clear()
            global_registry._subscriptions.clear()
            global_registry._discovered = False