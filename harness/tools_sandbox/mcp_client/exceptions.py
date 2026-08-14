"""Excepciones del paquete ``mcp_client``.

Extraido mecanicamente de ``mcp_client.py`` (regla AGR < 500 lineas).
Sin cambios de logica ni de firmas.
"""
from __future__ import annotations


class MCPConnectionError(Exception):
    """Raised when connection to an MCP server fails."""


class MCPToolError(Exception):
    """Raised when tool execution fails."""


class MCPTimeoutError(Exception):
    """Raised when a request times out."""
