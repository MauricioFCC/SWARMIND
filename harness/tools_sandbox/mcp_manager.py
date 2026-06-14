"""
MCP Manager — manages a pool of MCP client connections to multiple servers.

Provides a unified interface to discover and execute tools across
all registered MCP servers. Tools are resolved by name and routed
to the appropriate server automatically.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .mcp_client import MCPClient, MCPResult, MCPTool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_TTL = 60  # seconds


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""

    name: str
    url: str
    description: str = ""
    tools: List[str] = field(default_factory=list)
    enabled: bool = False
    install_hint: str = ""


# ---------------------------------------------------------------------------
# MCP Manager
# ---------------------------------------------------------------------------


class MCPManager:
    """
    Manages connections to multiple MCP servers and provides unified
    tool discovery and execution.

    Usage::

        manager = MCPManager()
        manager.load_servers("path/to/mcp_servers.yaml")

        # Enable a server
        manager.enable_server("filesystem")
        manager.connect_all()

        # Execute any tool across all servers
        result = manager.execute("read_file", {"path": "/tmp/test.txt"})

        # Get a tool by name
        tool = manager.get_tool("read_file")
    """

    def __init__(self):
        """Inicializa la instancia de la clase."""
        self._servers: Dict[str, MCPServerConfig] = {}
        self._clients: Dict[str, MCPClient] = {}
        self._tool_index: Dict[str, MCPTool] = {}  # tool_name -> MCPTool
        self._index_ts: float = 0.0
        self._cache_ttl: float = _DEFAULT_CACHE_TTL

    # ------------------------------------------------------------------
    # Server registration
    # ------------------------------------------------------------------

    def register_server(
        self,
        name: str,
        url: str,
        tools: Optional[List[str]] = None,
        enabled: bool = False,
        description: str = "",
        install_hint: str = "",
    ) -> None:
        """
        Register a new MCP server.

        Args:
            name: Unique server name.
            url: Server URL (e.g. http://localhost:3100).
            tools: List of tool names this server provides.
            enabled: Whether to auto-connect on startup.
            description: Human-readable description.
            install_hint: How to install this server.
        """
        self._servers[name] = MCPServerConfig(
            name=name,
            url=url,
            tools=tools or [],
            enabled=enabled,
            description=description,
            install_hint=install_hint,
        )
        logger.info("Registered MCP server '%s' at %s (enabled=%s)", name, url, enabled)

    def remove_server(self, name: str) -> None:
        """Remove a server and disconnect its client."""
        if name in self._clients:
            self._clients[name].disconnect()
            del self._clients[name]
        self._servers.pop(name, None)
        self._invalidate_index()

    def enable_server(self, name: str) -> None:
        """Enable a server (will connect on next ``connect_all``)."""
        if name in self._servers:
            self._servers[name].enabled = True
            logger.info("Enabled MCP server '%s'", name)

    def disable_server(self, name: str) -> None:
        """Disable and disconnect a server."""
        if name in self._clients:
            self._clients[name].disconnect()
            del self._clients[name]
        if name in self._servers:
            self._servers[name].enabled = False
        self._invalidate_index()

    def load_servers(self, config_path: str) -> int:
        """
        Load server definitions from a YAML file.

        Args:
            config_path: Path to mcp_servers.yaml.

        Returns:
            Number of servers loaded.
        """
        try:
            import yaml

            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            servers_raw = data.get("servers", [])
            count = 0
            for s in servers_raw:
                self.register_server(
                    name=s.get("name", f"server-{count}"),
                    url=s.get("url", ""),
                    tools=s.get("tools", []),
                    enabled=s.get("enabled", False),
                    description=s.get("description", ""),
                    install_hint=s.get("install_hint", ""),
                )
                count += 1

            logger.info("Loaded %d MCP servers from %s", count, config_path)
            # Auto-connect enabled servers
            self.connect_all()
            return count

        except Exception as exc:
            logger.error("Failed to load MCP servers: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect_all(self) -> int:
        """
        Connect to all enabled servers.

        Returns:
            Number of successful connections.
        """
        connected = 0
        for name, config in self._servers.items():
            if not config.enabled:
                continue
            if name in self._clients and self._clients[name].is_connected():
                connected += 1
                continue

            client = MCPClient()
            if client.connect(config.url):
                self._clients[name] = client
                connected += 1
                logger.info("Connected to MCP server '%s' at %s", name, config.url)
            else:
                logger.warning("Failed to connect to MCP server '%s'", name)

        if connected:
            self._invalidate_index()
        return connected

    def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        for name, client in self._clients.items():
            client.disconnect()
        self._clients.clear()
        self._invalidate_index()
        logger.info("Disconnected from all MCP servers.")

    def get_connected_servers(self) -> List[str]:
        """Return names of currently connected servers."""
        return [
            name
            for name, client in self._clients.items()
            if client.is_connected()
        ]

    # ------------------------------------------------------------------
    # Tool discovery
    # ------------------------------------------------------------------

    def list_all_tools(self) -> List[MCPTool]:
        """
        List all tools available across all connected servers.

        Results are cached for ``cache_ttl`` seconds.
        """
        if self._tool_index and (time.time() - self._index_ts) < self._cache_ttl:
            return list(self._tool_index.values())

        self._rebuild_index()
        return list(self._tool_index.values())

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """
        Find a tool by name across all connected servers.

        Args:
            name: Tool name to look up.

        Returns:
            ``MCPTool`` if found, ``None`` otherwise.
        """
        self._ensure_index()
        return self._tool_index.get(name)

    def find_server_for_tool(self, tool_name: str) -> Optional[str]:
        """Find which server provides a given tool."""
        for name, config in self._servers.items():
            if config.enabled and tool_name in config.tools:
                return name
        return None

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def execute(
        self,
        tool_name: str,
        params: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> MCPResult:
        """
        Execute a tool on the appropriate MCP server.

        The tool is resolved by name to the server that provides it.

        Args:
            tool_name: Name of the tool to execute.
            params: Parameters for the tool.
            timeout: Optional per-call timeout.

        Returns:
            ``MCPResult`` with execution details.
        """
        self._ensure_index()

        tool = self._tool_index.get(tool_name)
        if not tool:
            return MCPResult(
                success=False,
                output=None,
                tool_name=tool_name,
                server_name="",
                duration_ms=0.0,
                error=f"Tool '{tool_name}' not found in any connected server",
            )

        server_name = tool.server_name
        client = self._clients.get(server_name)
        if not client or not client.is_connected():
            return MCPResult(
                success=False,
                output=None,
                tool_name=tool_name,
                server_name=server_name,
                duration_ms=0.0,
                error=f"Server '{server_name}' is not connected",
            )

        return client.execute_tool(tool_name, params, timeout)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_index(self) -> None:
        """Rebuild tool index if stale or empty."""
        if not self._tool_index or (time.time() - self._index_ts) > self._cache_ttl:
            self._rebuild_index()

    def _rebuild_index(self) -> None:
        """Rebuild the tool index from all connected clients."""
        self._tool_index.clear()
        for server_name, client in self._clients.items():
            if not client.is_connected():
                continue
            try:
                tools = client.list_tools()
                for tool in tools:
                    tool.server_name = server_name
                    self._tool_index[tool.name] = tool
            except Exception as exc:
                logger.warning(
                    "Failed to list tools from '%s': %s", server_name, exc
                )

        self._index_ts = time.time()
        logger.debug(
            "Rebuilt tool index: %d tools from %d servers",
            len(self._tool_index),
            len(self._clients),
        )

    def _invalidate_index(self) -> None:
        """Force the tool index to be rebuilt on next access."""
        self._tool_index.clear()
        self._index_ts = 0.0

    def set_cache_ttl(self, ttl_seconds: float) -> None:
        """Set the tool index cache TTL."""
        self._cache_ttl = max(1.0, ttl_seconds)
