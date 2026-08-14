"""Mixin de discovery/cache de tools para ``MCPClient``.

Extraido mecanicamente de ``mcp_client.py`` (regla AGR < 500 lineas).
Contiene los metodos de listado y cache de tools (con politica de cache
del servidor) como mixin para que ``MCPClient`` (en ``core.py``)
conserve la misma API publica y privada sin cambios de logica ni firmas.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from .models import MCPTool

logger = logging.getLogger("harness.tools_sandbox.mcp_client")


class _ToolsMixin:
    """Metodos de tools/cache para ``MCPClient``."""

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
