"""Tipos del paquete ``mcp_client``: constantes + datos + excepciones.

Fusion mecanica de ``constants.py`` + ``models.py`` + ``exceptions.py``
(ADR: especialistas de arquitectura — 3 archivos <35L fusionados en uno;
sin cambios de logica, valores, nombres ni firmas).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Constantes (antes constants.py)
# ---------------------------------------------------------------------------
MCP_VERSION = "2025-03-26"  # MCP protocol version (legacy session-based)
STATELESS_VERSION = "2026-07-28"  # MCP stateless protocol version (spec 2026-07-28)
DEFAULT_TIMEOUT = 30  # seconds
MAX_RETRIES = 2
DEFAULT_STATELESS_TIMEOUT = 10.0  # seconds (connect_stateless)
STATELESS_DISCOVER_RPC = "server/discover"  # RPC stateless de descubrimiento
HEADER_METHOD = "Mcp-Method"  # Header que identifica el metodo JSON-RPC
HEADER_NAME = "Mcp-Name"  # Header que identifica el cliente MCP
MCP_CLIENT_NAME = "harness-mcp-client"

# ---------------------------------------------------------------------------
# Datos (antes models.py)
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
# Excepciones (antes exceptions.py)
# ---------------------------------------------------------------------------


class MCPConnectionError(Exception):
    """Raised when connection to an MCP server fails."""


class MCPToolError(Exception):
    """Raised when tool execution fails."""


class MCPTimeoutError(Exception):
    """Raised when a request times out."""
