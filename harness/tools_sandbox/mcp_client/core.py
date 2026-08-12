"""Clase principal ``MCPClient``.

Extraido mecanicamente de ``mcp_client.py`` (regla AGR < 500 lineas).
La clase conserva la misma API publica y privada; la conexion vive en el
mixin de ``connection.py`` y el discovery/cache de tools en ``tools.py``.
Sin cambios de logica.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from .connection import _ConnectionMixin
from .constants import (
    DEFAULT_TIMEOUT,
    HEADER_METHOD,
    HEADER_NAME,
    MCP_CLIENT_NAME,
    STATELESS_VERSION,
)
from .models import MCPResult, MCPTool
from .tools import _ToolsMixin

logger = logging.getLogger("harness.tools_sandbox.mcp_client")


class MCPClient(_ConnectionMixin, _ToolsMixin):
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
