"""Tipos de datos MCP: ``MCPTool`` y ``MCPResult``.

Extraido mecanicamente de ``mcp_client.py`` (regla AGR < 500 lineas).
Sin cambios de logica ni de firmas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
