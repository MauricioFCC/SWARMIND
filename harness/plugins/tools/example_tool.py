"""Example tools demonstrating the plugin pattern."""
from harness.plugins.registry import PluginBase, registry


@registry.register("greeter")
class GreeterTool(PluginBase):
    name = "greeter"
    description = "Saluda al usuario"
    def execute(self, name: str = "Mundo", **kwargs) -> str:
        return f"Hola {name}!"


@registry.register("echo")
class EchoTool(PluginBase):
    name = "echo"
    description = "Repite el texto"
    def execute(self, text: str = "", **kwargs) -> str:
        return text
