"""
MCP Client — Universal JSON-RPC client for MCP (Model Context Protocol) servers.

Implements the MCP protocol over HTTP/SSE (Server-Sent Events) as specified
by the Model Context Protocol standard.

Supports:
- Connect/disconnect to MCP servers
- List available tools
- Execute tools with parameters
- Timeout management
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MCP_VERSION = "2025-03-26"  # MCP protocol version
DEFAULT_TIMEOUT = 30  # seconds
MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class MCPTool:
    """An MCP tool exposed by a server."""

    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


@dataclass
class MCPResult:
    """Result of an MCP tool execution."""

    success: bool
    output: Any
    tool_name: str
    server_name: str
    duration_ms: float
    error: Optional[str] = None
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
        self._server_url: Optional[str] = None
        self._connected: bool = False
        self._default_timeout = default_timeout
        self._tools_cache: List[MCPTool] = []
        self._cache_ts: float = 0.0
        self._cache_ttl: float = 60.0  # seconds

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self, server_url: str, timeout: Optional[int] = None) -> bool:
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
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            result = resp.json()

            if "error" in result and result["error"]:
                logger.error("MCP initialize failed: %s", result["error"])
                return False

            self._server_url = url
            self._connected = True
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
        except Exception as exc:
            logger.error("MCP connection failed to %s: %s", url, exc)
            self._connected = False
            return False

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
                )
            except Exception:
                pass  # best-effort

        self._connected = False
        self._server_url = None
        self._tools_cache = []
        logger.info("MCP disconnected.")

    def is_connected(self) -> bool:
        """Check if the client is currently connected."""
        return self._connected

    # ------------------------------------------------------------------
    # Tool discovery
    # ------------------------------------------------------------------

    def list_tools(self, force_refresh: bool = False) -> List[MCPTool]:
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

    def _refresh_tools(self) -> List[MCPTool]:
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
            )
            resp.raise_for_status()
            data = resp.json()

            if "error" in data and data["error"]:
                logger.error("Failed to list tools: %s", data["error"])
                return []

            tools_raw = data.get("result", {}).get("tools", [])
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

        except Exception as exc:
            logger.error("Failed to refresh tools: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        timeout: Optional[int] = None,
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
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            elapsed = (time.perf_counter() - start) * 1000

            if "error" in data and data["error"]:
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

        except Exception as exc:
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
        params: Dict[str, Any],
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a JSON-RPC 2.0 request payload."""
        return {
            "jsonrpc": "2.0",
            "id": request_id or uuid.uuid4().hex[:12],
            "method": method,
            "params": params,
        }

    def set_cache_ttl(self, ttl_seconds: float) -> None:
        """Set the tool cache time-to-live."""
        self._cache_ttl = max(1.0, ttl_seconds)

    def clear_cache(self) -> None:
        """Force-clear the tool cache."""
        self._tools_cache = []
        self._cache_ts = 0.0
