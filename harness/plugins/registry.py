"""Tool Registry — Auto-discovery via import-time registration."""
from __future__ import annotations
import importlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


class PluginBase:
    """Base class for all plugins."""
    name: str = ""
    description: str = ""
    version: str = "0.1.0"

    def execute(self, **kwargs) -> Any:
        raise NotImplementedError


class ToolRegistry:
    """Central tool registry with auto-discovery."""

    def __init__(self):
        self._tools: Dict[str, Type[PluginBase]] = {}
        self._instances: Dict[str, PluginBase] = {}
        self._discovered: bool = False

    def register(self, name: Optional[str] = None) -> Callable:
        """Decorator to register a tool."""
        def decorator(cls: Type[PluginBase]) -> Type[PluginBase]:
            n = name or cls.__name__
            self._tools[n] = cls
            logger.debug("Registered: %s", n)
            return cls
        return decorator

    def get(self, name: str) -> Optional[PluginBase]:
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

    def discover_all(self, path: Optional[str] = None) -> int:
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
            except Exception as exc:
                logger.warning("Failed: %s: %s", py_file.name, exc)
        self._discovered = True
        logger.info("Discovered %d tools", count)
        return count

    def list_tools(self) -> List[Dict[str, Any]]:
        if not self._discovered:
            self.discover_all()
        return sorted(
            [{"name": n, "description": getattr(c, "description", ""), "class": c.__name__}
             for n, c in self._tools.items()],
            key=lambda t: t["name"],
        )

    def get_stats(self) -> Dict[str, Any]:
        return {"total": len(self._tools), "discovered": self._discovered, "tools": self.list_tools()}


registry = ToolRegistry()
