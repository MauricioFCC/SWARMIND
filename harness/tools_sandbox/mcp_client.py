"""
MCP Client â€” Universal JSON-RPC client for MCP (Model Context Protocol) servers.

Implements the MCP protocol over HTTP/SSE (Server-Sent Events) as specified
by the Model Context Protocol standard.

Supports:
- Connect/disconnect to MCP servers
- List available tools
- Execute tools with parameters
- Timeout management
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MCP_VERSION = "2025-03-26"  # MCP protocol version (legacy session-based)
STATELESS_VERSION = "2026-07-28"  # MCP stateless protocol version (spec 2026-07-28)
DEFAULT_TIMEOUT = 30  # seconds
MAX_RETRIES = 2
DEFAULT_STATELESS_TIMEOUT = 10.0  # seconds (connect_stateless)
STATELESS_DISCOVER_RPC = "server/discover"  # RPC stateless de descubrimiento
HEADER_METHOD = "Mcp-Method"  # Header que identifica el método JSON-RPC
HEADER_NAME = "Mcp-Name"  # Header que identifica el cliente MCP
MCP_CLIENT_NAME = "harness-mcp-client"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class MCPTool:
    """An MCP tool exposed by a server."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


@dataclass
class MCPResult:
    """Result of an MCP tool execution."""

    success: bool
    output: Any
    tool_name: str
    server_name: str
    duration_ms: float
    error: str | None = None
    request_id: str = ""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MCPConnectionError(Exception):
    """Raised when connection to an MCP server fails."""


class MCPToolError(Exception):
    """Raised when tool execution fails."""


class MCPTimeoutError(Exception):
    """Raised when a request times out."""


# ---------------------------------------------------------------------------
# MCP Client
# ---------------------------------------------------------------------------


class MCPClient:
    """
    Client for connecting to MCP (Model Context Protocol) servers.

    Communicates via JSON-RPC 2.0 over HTTP/SSE.

    Usage::

        client = MCPClient()
        if client.connect("http://localhost:3100"):
            tools = client.list_tools()
            result = client.execute_tool("read_file", {"path": "/tmp/test.txt"})
            client.disconnect()
    """

    def __init__(self, default_timeout: int = DEFAULT_TIMEOUT):
        """Inicializa la instancia de la clase."""
        self._server_url: str | None = None
        self._connected: bool = False
        self._stateless: bool = False
        self._default_timeout = default_timeout
        self._tools_cache: list[MCPTool] = []
        self._cache_ts: float = 0.0
        self._cache_ttl: float = 60.0  # seconds

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self, server_url: str, timeout: int | None = None) -> bool:
        """
        Connect to an MCP server.

        Performs a handshake using the MCP initialize method to verify
        the server is running and compatible.

        Args:
            server_url: URL of the MCP server (e.g. http://localhost:3100).
            timeout: Optional connection timeout in seconds.

        Returns:
            True if connection succeeded.
        """
        url = server_url.rstrip("/")
        timeout_s = timeout or self._default_timeout

        try:
            import requests

            # MCP initialize request
            payload = self._make_request("initialize", {
                "protocolVersion": MCP_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "harness-mcp-client",
                    "version": "1.0.0",
                },
            })

            resp = requests.post(
                f"{url}/jsonrpc",
                json=payload,
                timeout=timeout_s,
                headers=self._http_headers("initialize"),
            )
            resp.raise_for_status()
            result = resp.json()

            if result.get("error"):
                logger.error("MCP initialize failed: %s", result["error"])
                return False

            self._server_url = url
            self._connected = True
            self._stateless = False
            logger.info(
                "MCP connected to %s (server: %s)",
                url,
                result.get("result", {}).get("serverInfo", {}),
            )

            # Refresh tool cache
            self._refresh_tools()
            return True

        except ImportError:
            logger.error("requests library required for MCP client. pip install requests")
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("MCP connection failed to %s: %s", url, exc)
            self._connected = False
            self._stateless = False
            return False

    def connect_stateless(
        self,
        server_url: str,
        timeout: float | None = None,
    ) -> bool:
        """
        Conecta a un servidor MCP usando el protocolo stateless (spec 2026-07-28).

        Descubre las capacidades del servidor mediante el RPC ``server/discover``.
        Cada request es self-describing (versión + capabilities en ``_meta``);
        no se requiere handshake ``initialize`` ni ``Mcp-Session-Id``.

        Args:
            server_url: URL del servidor MCP (ej. http://localhost:3100).
            timeout: Timeout de conexión en segundos; por defecto usa
                ``DEFAULT_STATELESS_TIMEOUT``.

        Returns:
            True si el servidor aceptó el descubrimiento stateless; False en
            caso contrario (red, HTTP o error JSON-RPC).

        Raises:
            No lanza excepciones: cualquier fallo se registra con logger y
            devuelve False (WHAT+WHY+WHERE en el mensaje).
        """
        url = server_url.rstrip("/")
        timeout_s = timeout if timeout is not None else DEFAULT_STATELESS_TIMEOUT

        result = self._stateless_discover(url, timeout_s)
        if result is None:
            self._connected = False
            self._stateless = False
            return False

        self._server_url = url
        self._connected = True
        self._stateless = True
        logger.info(
            "MCP stateless connected to %s (server: %s)",
            url,
            result.get("result", {}),
        )
        return True

    def _stateless_discover(
        self,
        server_url: str,
        timeout_s: float,
    ) -> dict[str, Any] | None:
        """
        Ejecuta el RPC stateless ``server/discover`` y devuelve la respuesta.

        Args:
            server_url: URL del servidor MCP ya normalizada (sin trailing slash).
            timeout_s: Timeout de la petición en segundos.

        Returns:
            La respuesta JSON-RPC completa si el descubrimiento fue exitoso;
            None si hubo error de red, HTTP o error JSON-RPC del servidor.
        """
        try:
            import requests

            payload = self._make_request(STATELESS_DISCOVER_RPC, {}, stateless=True)
            resp = requests.post(
                f"{server_url}/jsonrpc",
                json=payload,
                timeout=timeout_s,
                headers=self._http_headers(STATELESS_DISCOVER_RPC),
            )
            resp.raise_for_status()
            result = resp.json()

            if result.get("error"):
                logger.error(
                    "MCP stateless discover failed for %s: %s",
                    server_url,
                    result["error"],
                )
                return None

            return result

        except ImportError:
            logger.error("requests library required for MCP client. pip install requests")
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error("MCP stateless connect failed to %s: %s", server_url, exc)
            return None

    def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self._connected and self._server_url:
            try:
                payload = self._make_request("shutdown", {})
                import requests

                requests.post(
                    f"{self._server_url}/jsonrpc",
                    json=payload,
                    timeout=5,
                    headers=self._http_headers("shutdown"),
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("MCP best-effort operation failed: %s", exc)

        self._connected = False
        self._stateless = False
        self._server_url = None
        self._tools_cache = []
        logger.info("MCP disconnected.")

    def is_connected(self) -> bool:
        """Check if the client is currently connected."""
        return self._connected

    # ------------------------------------------------------------------
    # Tool discovery
    # ------------------------------------------------------------------

    def list_tools(self, force_refresh: bool = False) -> list[MCPTool]:
        """
        List available tools from the MCP server.

        Results are cached for ``cache_ttl`` seconds.

        Args:
            force_refresh: If True, bypass cache.

        Returns:
            List of ``MCPTool`` descriptors.
        """
        if not self._connected:
            logger.warning("Cannot list tools: not connected.")
            return []

        now = time.time()
        if (
            not force_refresh
            and self._tools_cache
            and (now - self._cache_ts) < self._cache_ttl
        ):
            return self._tools_cache

        return self._refresh_tools()

    def _refresh_tools(self) -> list[MCPTool]:
        """Fetch available tools from the server and update cache."""
        if not self._server_url:
            return []

        try:
            import requests

            payload = self._make_request("tools/list", {})
            resp = requests.post(
                f"{self._server_url}/jsonrpc",
                json=payload,
                timeout=self._default_timeout,
                headers=self._http_headers("tools/list"),
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("error"):
                logger.error("Failed to list tools: %s", data["error"])
                return []

            result = data.get("result", {})
            self._apply_cache_policy(result, data)

            tools_raw = result.get("tools", [])
            tools = []
            for t in tools_raw:
                tools.append(MCPTool(
                    name=t.get("name", "unknown"),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                    server_name=self._server_url,
                ))

            self._tools_cache = tools
            self._cache_ts = time.time()
            logger.debug("Refreshed tool cache: %d tools", len(tools))
            return tools

        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to refresh tools: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def execute_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
        timeout: int | None = None,
    ) -> MCPResult:
        """
        Execute a tool on the MCP server.

        Args:
            tool_name: Name of the tool to execute.
            params: Parameters to pass to the tool.
            timeout: Optional per-call timeout (overrides default).

        Returns:
            ``MCPResult`` with execution details.
        """
        start = time.perf_counter()
        request_id = uuid.uuid4().hex[:12]

        if not self._connected or not self._server_url:
            elapsed = (time.perf_counter() - start) * 1000
            return MCPResult(
                success=False,
                output=None,
                tool_name=tool_name,
                server_name=self._server_url or "",
                duration_ms=round(elapsed, 2),
                error="Not connected to MCP server",
                request_id=request_id,
            )

        try:
            import requests

            payload = self._make_request(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": params,
                },
                request_id=request_id,
            )

            timeout_s = timeout or self._default_timeout
            resp = requests.post(
                f"{self._server_url}/jsonrpc",
                json=payload,
                timeout=timeout_s,
                headers=self._http_headers("tools/call"),
            )
            resp.raise_for_status()
            data = resp.json()

            elapsed = (time.perf_counter() - start) * 1000

            if data.get("error"):
                return MCPResult(
                    success=False,
                    output=None,
                    tool_name=tool_name,
                    server_name=self._server_url,
                    duration_ms=round(elapsed, 2),
                    error=str(data["error"]),
                    request_id=request_id,
                )

            result = data.get("result", {})
            content = result.get("content", [])
            is_error = result.get("isError", False)

            # Extract text content
            output = None
            for item in content:
                if item.get("type") == "text":
                    output = item.get("text", "")
                    break
            if output is None and content:
                output = content  # fallback: return full content array

            return MCPResult(
                success=not is_error,
                output=output,
                tool_name=tool_name,
                server_name=self._server_url,
                duration_ms=round(elapsed, 2),
                error=None if not is_error else "Tool returned error",
                request_id=request_id,
            )

        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - start) * 1000
            return MCPResult(
                success=False,
                output=None,
                tool_name=tool_name,
                server_name=self._server_url or "",
                duration_ms=round(elapsed, 2),
                error=str(exc),
                request_id=request_id,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_request(
        self,
        method: str,
        params: dict[str, Any],
        request_id: str | None = None,
        *,
        stateless: bool | None = None,
    ) -> dict[str, Any]:
        """
        Construye un payload de request JSON-RPC 2.0.

        Args:
            method: Método JSON-RPC (ej. ``tools/list``).
            params: Parámetros del método.
            request_id: ID opcional del request; si no se provee se genera uno.
            stateless: Si True inyecta ``_meta`` self-describing; si False no lo
                hace; si None (default) sigue el estado del cliente
                (``self._stateless``).

        Returns:
            Dict con el payload JSON-RPC 2.0 listo para serializar.
        """
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id or uuid.uuid4().hex[:12],
            "method": method,
            "params": params,
        }
        use_stateless = self._stateless if stateless is None else stateless
        if use_stateless:
            payload["params"] = {**params, "_meta": self._stateless_meta()}
        return payload

    def _http_headers(self, method: str) -> dict[str, str]:
        """
        Construye los headers HTTP para un request JSON-RPC MCP.

        Incluye los headers ``Mcp-Method`` y ``Mcp-Name`` exigidos por el
        protocolo stateless 2026-07-28 (se envían en ambos modos).

        Args:
            method: Método JSON-RPC del request (ej. ``tools/list``).

        Returns:
            Dict con los headers HTTP del request.
        """
        return {
            "Content-Type": "application/json",
            HEADER_METHOD: method,
            HEADER_NAME: MCP_CLIENT_NAME,
        }

    def _stateless_meta(self) -> dict[str, Any]:
        """
        Construye el bloque ``_meta`` self-describing de un request stateless.

        Returns:
            Dict con la versión del protocolo stateless y las capabilities
            del cliente (vacías por defecto).
        """
        return {
            "protocolVersion": STATELESS_VERSION,
            "capabilities": {},
        }

    def _apply_cache_policy(
        self,
        result: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        """
        Aplica la política de caché cacheable declarada por el servidor.

        Si la respuesta de list_tools incluye ``_meta.ttlMs``, ese TTL (en
        milisegundos) se convierte a segundos y se usa en lugar del
        ``_cache_ttl`` por defecto.

        Args:
            result: Objeto ``result`` de la respuesta JSON-RPC.
            response: Respuesta JSON-RPC completa (por si ``_meta`` viene a
                nivel raíz).

        Returns:
            None. Actualiza ``self._cache_ttl`` si el servidor lo indica.
        """
        if not isinstance(result, dict):
            return
        meta = result.get("_meta") or response.get("_meta") or {}
        ttl_ms = meta.get("ttlMs")
        if ttl_ms is not None:
            self._cache_ttl = max(1.0, float(ttl_ms) / 1000.0)
            logger.debug(
                "Server cache policy: ttlMs=%s -> cache_ttl=%.2fs",
                ttl_ms,
                self._cache_ttl,
            )

    def set_cache_ttl(self, ttl_seconds: float) -> None:
        """Set the tool cache time-to-live."""
        self._cache_ttl = max(1.0, ttl_seconds)

    def clear_cache(self) -> None:
        """Force-clear the tool cache."""
        self._tools_cache = []
        self._cache_ts = 0.0

