"""
Plugin System — Auto-discovery de tools y extensiones.

Inspirado en Hermes Agent: los tools se registran llamando a
registry.register() al importarse. discover_all() importa todos
los .py en harness/plugins/tools/ automaticamente.

Uso:
    @registry.register("my-tool")
    class MyTool(PluginBase):
        def execute(self, **kwargs): ...
    
    registry.discover_all()
    tool = registry.get("my-tool")
    tool.execute(...)
"""
from harness.plugins.registry import PluginBase, registry

ToolRegistry = registry  # es una instancia, no una clase

__all__ = ["PluginBase", "ToolRegistry", "registry"]
