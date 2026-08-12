"""Constantes del paquete ``mcp_client``.

Extraido mecanicamente de ``mcp_client.py`` (regla AGR < 500 lineas).
Sin cambios de logica: los valores y nombres son identicos al original.
"""
from __future__ import annotations

MCP_VERSION = "2025-03-26"  # MCP protocol version (legacy session-based)
STATELESS_VERSION = "2026-07-28"  # MCP stateless protocol version (spec 2026-07-28)
DEFAULT_TIMEOUT = 30  # seconds
MAX_RETRIES = 2
DEFAULT_STATELESS_TIMEOUT = 10.0  # seconds (connect_stateless)
STATELESS_DISCOVER_RPC = "server/discover"  # RPC stateless de descubrimiento
HEADER_METHOD = "Mcp-Method"  # Header que identifica el método JSON-RPC
HEADER_NAME = "Mcp-Name"  # Header que identifica el cliente MCP
MCP_CLIENT_NAME = "harness-mcp-client"
