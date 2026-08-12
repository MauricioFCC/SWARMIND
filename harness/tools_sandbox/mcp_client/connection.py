"""Mixin de gestion de conexion para ``MCPClient``.

Extraido mecanicamente de ``mcp_client.py`` (regla AGR < 500 lineas).
Contiene los metodos de conexion (session-based y stateless 2026-07-28)
como mixin para que ``MCPClient`` (en ``core.py``) conserve la misma API
publica y privada sin cambios de logica ni de firmas.
"""
from __future__ import annotations

import logging
from typing import Any

from .constants import (
    DEFAULT_STATELESS_TIMEOUT,
    MCP_VERSION,
    STATELESS_DISCOVER_RPC,
)

logger = logging.getLogger("harness.tools_sandbox.mcp_client")


class _ConnectionMixin:
    """Metodos de conexion/desconexion para ``MCPClient``."""

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
