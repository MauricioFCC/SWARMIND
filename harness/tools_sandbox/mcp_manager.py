"""
MCP Manager — manages a pool of MCP client connections to multiple servers.

Provides a unified interface to discover and execute tools across
all registered MCP servers. Tools are resolved by name and routed
to the appropriate server automatically.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from .mcp_client import MCPClient, MCPResult, MCPTool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_TTL = 60  # seconds

#: Transportes soportados por un servidor MCP.
_VALID_TRANSPORTS: tuple[str, ...] = ("http", "stdio")
#: Ubicación de la validación de transporte (para mensajes WHAT/WHY/WHERE).
_CONFIG_WHERE = "harness/tools_sandbox/mcp_manager.py::MCPServerConfig.__post_init__"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MCPConfigError(ValueError):
    """Error de configuración de un servidor MCP (transporte/endpoint inválido).

    Subclase de ``ValueError`` para que el llamador pueda capturar el tipo
    específico o un ``ValueError`` genérico. El mensaje siempre incluye
    WHAT (qué falta), WHY (por qué es obligatorio) y WHERE (dónde se valida).
    """


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class MCPServerConfig:
    """Configuración de un servidor MCP con transporte dual (http/stdio).

    - Transporte ``http``: el servidor se alcanza por red en ``url``.
    - Transporte ``stdio``: el servidor se lanza como subproceso
      ``command`` + ``args`` con ``env`` extra (ej. REA:
      ``npx -y rea-agents@latest mcp``).

    Attributes:
        name: Nombre único del servidor.
        url: URL del servidor (obligatoria si ``transport == "http"``).
        description: Descripción legible.
        tools: Nombres de herramientas que expone el servidor.
        enabled: Si se auto-conecta al cargar.
        install_hint: Cómo instalar/registrar el servidor.
        transport: ``"http"`` (red) o ``"stdio"`` (subproceso).
        command: Ejecutable a lanzar (obligatorio si ``transport == "stdio"``).
        args: Argumentos del ejecutable ``command``.
        env: Variables de entorno extra para el subproceso stdio.

    Raises:
        MCPConfigError: si ``transport`` es desconocido, si ``stdio`` no
            define ``command`` o si ``http`` no define ``url``.
    """

    name: str
    url: str = ""
    description: str = ""
    tools: list[str] = field(default_factory=list)
    enabled: bool = False
    install_hint: str = ""
    transport: Literal["http", "stdio"] = "http"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Valida la coherencia transporte ↔ endpoint con WHAT/WHY/WHERE.

        Raises:
            MCPConfigError: si falta el endpoint exigido por el transporte.
        """
        if self.transport not in _VALID_TRANSPORTS:
            raise MCPConfigError(
                f"WHAT: transport '{self.transport}' desconocido "
                f"(esperado uno de {list(_VALID_TRANSPORTS)}) para el servidor "
                f"'{self.name}'; WHY: el manager solo sabe conectar http o stdio; "
                f"WHERE: {_CONFIG_WHERE}."
            )
        if self.transport == "stdio":
            if not self.command or not self.command.strip():
                raise MCPConfigError(
                    f"WHAT: 'command' es obligatorio para transport='stdio' "
                    f"(servidor '{self.name}'); WHY: un servidor stdio corre como "
                    f"subproceso y necesita un ejecutable que lanzar; "
                    f"WHERE: {_CONFIG_WHERE}."
                )
        elif not self.url or not self.url.strip():
            raise MCPConfigError(
                f"WHAT: 'url' es obligatorio para transport='http' "
                f"(servidor '{self.name}'); WHY: un servidor http se alcanza por "
                f"red en una URL; WHERE: {_CONFIG_WHERE}."
            )

    def is_stdio(self) -> bool:
        """Indica si el servidor usa transporte stdio (subproceso).

        Returns:
            True si ``transport == "stdio"``; False si es http.
        """
        return self.transport == "stdio"


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

    def __init__(
        self,
        circuit_threshold: int = 5,
        circuit_cooldown: float = 60.0,
        strict_security: bool = False,
    ) -> None:
        """Inicializa el manager con circuit breaker por servidor."""
        self._servers: dict[str, MCPServerConfig] = {}
        self._clients: dict[str, MCPClient] = {}
        self._tool_index: dict[str, MCPTool] = {}  # tool_name -> MCPTool
        self._index_ts: float = 0.0
        self._cache_ttl: float = _DEFAULT_CACHE_TTL
        self._circuit_threshold: int = max(1, int(circuit_threshold))
        self._circuit_cooldown: float = max(1.0, float(circuit_cooldown))
        self._circuit_state: dict[str, dict[str, Any]] = {}
        self._strict_security: bool = bool(strict_security)

    # ------------------------------------------------------------------
    # Server registration
    # ------------------------------------------------------------------

    def register_server(
        self,
        name: str,
        url: str = "",
        tools: list[str] | None = None,
        enabled: bool = False,
        description: str = "",
        install_hint: str = "",
        transport: Literal["http", "stdio"] = "http",
        command: str = "",
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """
        Register a new MCP server (transporte http o stdio).

        Args:
            name: Unique server name.
            url: Server URL (e.g. http://localhost:3100). Obligatoria para http.
            tools: List of tool names this server provides.
            enabled: Whether to auto-connect on startup.
            description: Human-readable description.
            install_hint: How to install this server.
            transport: ``"http"`` (red) o ``"stdio"`` (subproceso).
            command: Ejecutable a lanzar. Obligatorio para stdio.
            args: Argumentos del ejecutable ``command`` (stdio).
            env: Variables de entorno extra para el subproceso (stdio).

        Raises:
            MCPConfigError: si la configuración no es coherente (ver
                :class:`MCPServerConfig`).
        """
        self._servers[name] = MCPServerConfig(
            name=name,
            url=url,
            tools=tools or [],
            enabled=enabled,
            description=description,
            install_hint=install_hint,
            transport=transport,
            command=command,
            args=args or [],
            env=env or {},
        )
        target = f"command={command!r}" if transport == "stdio" else f"url={url}"
        logger.info(
            "Registered MCP server '%s' (%s: %s, enabled=%s)",
            name,
            transport,
            target,
            enabled,
        )

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
                    transport=s.get("transport", "http"),
                    command=s.get("command", ""),
                    args=s.get("args", []),
                    env=s.get("env", {}),
                )
                count += 1

            logger.info("Loaded %d MCP servers from %s", count, config_path)
            # Auto-connect enabled servers
            self.connect_all()
            return count

        except Exception as exc:  # noqa: BLE001
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
            if self.is_circuit_open(name):
                logger.info("Skipping '%s' (circuit open)", name)
                continue
            if self._strict_security:
                critical = [f for f in self.security_scan_server(name) if getattr(f, 'severity', '') == 'critical']
                if critical:
                    logger.warning("Skipping '%s' (security findings: %d)", name, len(critical))
                    self.record_failure(name)
                    continue
            if name in self._clients and self._clients[name].is_connected():
                connected += 1
                continue

            client = MCPClient()
            if config.is_stdio():
                connected_ok = client.connect_stdio(
                    config.command, config.args, config.env
                )
                where = f"stdio:{config.command}"
            else:
                connected_ok = client.connect(config.url)
                where = config.url

            if connected_ok:
                self._clients[name] = client
                connected += 1
                self.record_success(name)
                logger.info("Connected to MCP server '%s' at %s", name, where)
            else:
                self.record_failure(name)
                logger.warning("Failed to connect to MCP server '%s'", name)

        if connected:
            self._invalidate_index()
        return connected

    def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        for client in self._clients.values():
            client.disconnect()
        self._clients.clear()
        self._invalidate_index()
        logger.info("Disconnected from all MCP servers.")

    def get_connected_servers(self) -> list[str]:
        """Return names of currently connected servers."""
        return [
            name
            for name, client in self._clients.items()
            if client.is_connected()
        ]

    # ------------------------------------------------------------------
    # Tool discovery
    # ------------------------------------------------------------------

    def list_all_tools(self) -> list[MCPTool]:
        """
        List all tools available across all connected servers.

        Results are cached for ``cache_ttl`` seconds.
        """
        if self._tool_index and (time.time() - self._index_ts) < self._cache_ttl:
            return list(self._tool_index.values())

        self._rebuild_index()
        return list(self._tool_index.values())

    def get_tool(self, name: str) -> MCPTool | None:
        """
        Find a tool by name across all connected servers.

        Args:
            name: Tool name to look up.

        Returns:
            ``MCPTool`` if found, ``None`` otherwise.
        """
        self._ensure_index()
        return self._tool_index.get(name)

    def find_server_for_tool(self, tool_name: str) -> str | None:
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
        params: dict[str, Any],
        timeout: int | None = None,
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
        if self.is_circuit_open(server_name):
            return MCPResult(
                success=False,
                output=None,
                tool_name=tool_name,
                server_name=server_name,
                duration_ms=0.0,
                error=f"Circuit open for server '{server_name}'",
            )
        client = self._clients.get(server_name)
        if not client or not client.is_connected():
            self.record_failure(server_name)
            return MCPResult(
                success=False,
                output=None,
                tool_name=tool_name,
                server_name=server_name,
                duration_ms=0.0,
                error=f"Server '{server_name}' is not connected",
            )

        result = client.execute_tool(tool_name, params, timeout)
        if getattr(result, "success", False):
            self.record_success(server_name)
        else:
            self.record_failure(server_name)
        return result

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
            except Exception as exc:  # noqa: BLE001
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

    # ------------------------------------------------------------------
    # Circuit breaker helpers
    # ------------------------------------------------------------------

    def _circuit(self, server_name: str) -> dict[str, Any]:
        state = self._circuit_state.get(server_name)
        if state is None:
            state = {'failures': 0, 'opened_at': None, 'state': 'closed'}
            self._circuit_state[server_name] = state
        return state

    def is_circuit_open(self, server_name: str) -> bool:
        import time as _t
        st = self._circuit(server_name)
        if st['state'] != 'open':
            return False
        opened_at = st.get('opened_at') or 0.0
        if (_t.monotonic() - opened_at) >= self._circuit_cooldown:
            st['state'] = 'half_open'
            return False
        return True

    def record_success(self, server_name: str) -> None:
        st = self._circuit(server_name)
        st['failures'] = 0
        st['opened_at'] = None
        st['state'] = 'closed'

    def record_failure(self, server_name: str) -> None:
        st = self._circuit(server_name)
        st['failures'] = int(st.get('failures', 0)) + 1
        if st['failures'] >= self._circuit_threshold and st['state'] != 'open':
            import time as _t
            st['state'] = 'open'
            st['opened_at'] = _t.monotonic()

    def reset_circuit(self, server_name: str) -> None:
        self._circuit_state.pop(server_name, None)

    def circuit_state(self, server_name: str) -> str:
        return str(self._circuit(server_name).get('state', 'closed'))

    # ------------------------------------------------------------------
    # Reliability helpers
    # ------------------------------------------------------------------

    def health_check(self, server_name: str) -> bool:
        cfg = self._servers.get(server_name)
        if cfg is None:
            return False
        client = self._clients.get(server_name)
        if client is None or not client.is_connected():
            if cfg.is_stdio():
                new_client = MCPClient()
                ok = new_client.connect_stdio(cfg.command, cfg.args, cfg.env)
            else:
                new_client = MCPClient()
                ok = new_client.connect(cfg.url)
            if not ok:
                self.record_failure(server_name)
                return False
            self._clients[server_name] = new_client
            client = new_client
        try:
            client.list_tools()
        except Exception:  # noqa: BLE001
            self.record_failure(server_name)
            return False
        self.record_success(server_name)
        return True

    def reconnect(self, server_name: str) -> bool:
        cfg = self._servers.get(server_name)
        if cfg is None:
            return False
        if server_name in self._clients:
            try:
                self._clients[server_name].disconnect()
            except Exception:  # noqa: BLE001, S110
                pass
            del self._clients[server_name]
        self._invalidate_index()
        if cfg.is_stdio():
            client = MCPClient()
            ok = client.connect_stdio(cfg.command, cfg.args, cfg.env)
        else:
            client = MCPClient()
            ok = client.connect(cfg.url)
        if ok:
            self._clients[server_name] = client
            self.record_success(server_name)
        else:
            self.record_failure(server_name)
        return ok

    def execute_with_retry(
        self,
        tool_name: str,
        params: dict[str, Any],
        retries: int = 2,
        backoff: float = 0.5,
        timeout: int | None = None,
    ) -> MCPResult:
        import time as _t
        last: MCPResult | None = None
        attempts = max(1, int(retries) + 1)
        for attempt in range(attempts):
            result = self.execute(tool_name, params, timeout=timeout)
            last = result
            if result.success:
                return result
            if attempt < attempts - 1:
                delay = max(0.0, float(backoff)) * (attempt + 1)
                _t.sleep(delay)
        assert last is not None
        return last

    # ------------------------------------------------------------------
    # Security (OWASP MCP Top-10)
    # ------------------------------------------------------------------

    def _server_entry_for_scan(self, cfg: MCPServerConfig) -> dict[str, Any]:
        entry: dict[str, Any] = {}
        if cfg.is_stdio():
            entry['command'] = [cfg.command, *cfg.args]
        else:
            entry['url'] = cfg.url
        if cfg.env:
            entry['env'] = dict(cfg.env)
        return entry

    def security_scan_server(self, name: str) -> list[Any]:
        try:
            from harness.security.mcp_security_scan import _scan_server
        except Exception:  # noqa: BLE001
            return []
        cfg = self._servers.get(name)
        if cfg is None:
            return []
        try:
            return list(_scan_server(name, self._server_entry_for_scan(cfg)))
        except Exception:  # noqa: BLE001
            return []

    def security_scan(self) -> list[Any]:
        findings: list[Any] = []
        for name in list(self._servers.keys()):
            findings.extend(self.security_scan_server(name))
        return findings

    @classmethod
    def wired(cls, config_path: Any = None, base_dir: Any = None) -> MCPManager:
        """Factory: manager cargado + bridge inter-proyecto cableado."""
        m = cls()
        if config_path is not None:
            try:
                m.load_servers(str(config_path))
            except Exception:  # noqa: BLE001, S110
                pass
        try:
            from .mcp_project_bridge import register_project_bridge
            register_project_bridge(m, base_dir=base_dir)
        except Exception:  # noqa: BLE001, S110
            pass
        return m
