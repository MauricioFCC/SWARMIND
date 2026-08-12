"""MCP Client — Universal JSON-RPC client for MCP (Model Context Protocol) servers.

Este paquete reemplaza al modulo ``mcp_client.py`` (regla AGR: archivo
< 500 lineas). Todos los simbolos publicos del modulo original se
re-exportan desde aqui, por lo que los imports existentes
(``from harness.tools_sandbox.mcp_client import MCPClient``) siguen
funcionando identicos y los parches de tests que apuntan a
``harness.tools_sandbox.mcp_client.X`` siguen afectando al paquete.

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

from .constants import (
    DEFAULT_STATELESS_TIMEOUT,
    DEFAULT_TIMEOUT,
    HEADER_METHOD,
    HEADER_NAME,
    MAX_RETRIES,
    MCP_CLIENT_NAME,
    MCP_VERSION,
    STATELESS_DISCOVER_RPC,
    STATELESS_VERSION,
)
from .core import MCPClient
from .exceptions import MCPConnectionError, MCPTimeoutError, MCPToolError
from .models import MCPResult, MCPTool

logger = logging.getLogger("harness.tools_sandbox.mcp_client")

__all__ = [
    "DEFAULT_STATELESS_TIMEOUT",
    "DEFAULT_TIMEOUT",
    "HEADER_METHOD",
    "HEADER_NAME",
    "MAX_RETRIES",
    "MCP_CLIENT_NAME",
    "MCP_VERSION",
    "STATELESS_DISCOVER_RPC",
    "STATELESS_VERSION",
    "MCPClient",
    "MCPConnectionError",
    "MCPResult",
    "MCPTimeoutError",
    "MCPTool",
    "MCPToolError",
    "logger",
]
