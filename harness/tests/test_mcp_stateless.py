"""
Tests para el modo stateless del MCPClient (spec MCP 2026-07-28, ADR-0041 H1).

Cubre:
- Constantes nombradas del modo stateless (STATELESS_DISCOVER_RPC,
  HEADER_METHOD, HEADER_NAME, DEFAULT_STATELESS_TIMEOUT).
- connect_stateless: RPC server/discover, flags de estado, fallos y timeouts.
- Requests self-describing con ``_meta`` (versión + capabilities).
- Catálogos cacheables: respeta ``ttlMs``/``cacheScope`` del servidor.
- Headers ``Mcp-Method``/``Mcp-Name`` en todos los modos.
- Fallback legacy: ``connect()`` sigue usando ``initialize``.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from harness.tools_sandbox.mcp_client import (
    DEFAULT_STATELESS_TIMEOUT,
    HEADER_METHOD,
    HEADER_NAME,
    STATELESS_DISCOVER_RPC,
    MCPClient,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _mock_response(json_data: dict) -> MagicMock:
    """Crea un mock de respuesta HTTP con el JSON indicado."""
    m = MagicMock()
    m.json.return_value = json_data
    return m


@pytest.fixture
def client() -> MCPClient:
    """Fixture: MCPClient con valores por defecto."""
    return MCPClient()


# ===========================================================================
# Tests: Constantes del modo stateless
# ===========================================================================


class TestStatelessConstants:
    """Tests de las constantes nombradas del modo stateless."""

    def test_discover_rpc_constant(self) -> None:
        """STATELESS_DISCOVER_RPC debe ser 'server/discover'."""
        assert STATELESS_DISCOVER_RPC == "server/discover"

    def test_header_constants(self) -> None:
        """Los nombres de header deben ser Mcp-Method y Mcp-Name."""
        assert HEADER_METHOD == "Mcp-Method"
        assert HEADER_NAME == "Mcp-Name"

    def test_default_stateless_timeout(self) -> None:
        """DEFAULT_STATELESS_TIMEOUT debe ser 10.0 segundos."""
        assert DEFAULT_STATELESS_TIMEOUT == 10.0

    def test_new_client_starts_session_based(self) -> None:
        """Un cliente nuevo no está en modo stateless."""
        c = MCPClient()
        assert c._stateless is False


# ===========================================================================
# Tests: connect_stateless
# ===========================================================================


class TestConnectStateless:
    """Tests del método connect_stateless()."""

    def test_connect_stateless_success(self) -> None:
        """Éxito de server/discover debe conectar en modo stateless."""
        import requests

        mock_response = _mock_response({
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "protocolVersion": "2026-07-28",
                "capabilities": {"tools": {}},
            },
        })
        with patch.object(requests, "post", return_value=mock_response) as mock_post:
            c = MCPClient()
            result = c.connect_stateless("http://localhost:3100")

        assert result is True
        assert c._connected is True
        assert c._stateless is True
        assert c._server_url == "http://localhost:3100"
        payload = mock_post.call_args[1]["json"]
        assert payload["method"] == STATELESS_DISCOVER_RPC
        # Sin initialize ni session id obligatorios
        assert payload["method"] != "initialize"
        assert "sessionId" not in payload

    def test_connect_stateless_self_describing_meta(self) -> None:
        """El request stateless debe incluir _meta con versión y capabilities."""
        import requests

        mock_response = _mock_response({"jsonrpc": "2.0", "id": "1", "result": {}})
        with patch.object(requests, "post", return_value=mock_response) as mock_post:
            c = MCPClient()
            c.connect_stateless("http://localhost:3100")

        payload = mock_post.call_args[1]["json"]
        meta = payload["params"]["_meta"]
        assert meta["protocolVersion"] == "2026-07-28"
        assert "capabilities" in meta

    def test_connect_stateless_error_response(self) -> None:
        """Un error JSON-RPC en server/discover debe retornar False."""
        import requests

        mock_response = _mock_response({
            "jsonrpc": "2.0",
            "id": "1",
            "error": {"code": -32601, "message": "Method not found"},
        })
        with patch.object(requests, "post", return_value=mock_response):
            c = MCPClient()
            result = c.connect_stateless("http://localhost:3100")

        assert result is False
        assert c._connected is False
        assert c._stateless is False

    def test_connect_stateless_http_error(self) -> None:
        """Una excepción de red debe retornar False."""
        import requests

        with patch.object(requests, "post", side_effect=Exception("Connection refused")):
            c = MCPClient()
            result = c.connect_stateless("http://localhost:3100")

        assert result is False
        assert c._connected is False

    def test_connect_stateless_default_timeout(self) -> None:
        """connect_stateless debe usar DEFAULT_STATELESS_TIMEOUT por defecto."""
        import requests

        mock_response = _mock_response({"jsonrpc": "2.0", "id": "1", "result": {}})
        with patch.object(requests, "post", return_value=mock_response) as mock_post:
            c = MCPClient()
            c.connect_stateless("http://localhost:3100")

        assert mock_post.call_args[1]["timeout"] == DEFAULT_STATELESS_TIMEOUT

    def test_connect_stateless_custom_timeout(self) -> None:
        """connect_stateless debe aceptar timeout personalizado."""
        import requests

        mock_response = _mock_response({"jsonrpc": "2.0", "id": "1", "result": {}})
        with patch.object(requests, "post", return_value=mock_response) as mock_post:
            c = MCPClient()
            c.connect_stateless("http://localhost:3100", timeout=3.5)

        assert mock_post.call_args[1]["timeout"] == 3.5

    def test_connect_stateless_trailing_slash(self) -> None:
        """connect_stateless debe eliminar trailing slash de la URL."""
        import requests

        mock_response = _mock_response({"jsonrpc": "2.0", "id": "1", "result": {}})
        with patch.object(requests, "post", return_value=mock_response) as mock_post:
            c = MCPClient()
            c.connect_stateless("http://localhost:3100/")

        assert c._server_url == "http://localhost:3100"
        assert mock_post.call_args[0][0] == "http://localhost:3100/jsonrpc"

    def test_connect_legacy_fallback_preserved(self) -> None:
        """connect() legacy debe seguir usando initialize (fallback preservado)."""
        import requests

        mock_init = _mock_response({
            "jsonrpc": "2.0",
            "id": "1",
            "result": {"serverInfo": {"name": "legacy"}, "capabilities": {}},
        })
        mock_tools = _mock_response({
            "jsonrpc": "2.0", "id": "2", "result": {"tools": []},
        })
        with patch.object(requests, "post", side_effect=[mock_init, mock_tools]) as mock_post:
            c = MCPClient()
            result = c.connect("http://localhost:3100")

        assert result is True
        assert c._connected is True
        assert c._stateless is False  # legacy NO es stateless
        assert mock_post.call_args_list[0][1]["json"]["method"] == "initialize"


# ===========================================================================
# Tests: Catálogos cacheables (ttlMs/cacheScope)
# ===========================================================================


class TestCacheableCatalogs:
    """Tests de catálogos cacheables con ttlMs/cacheScope."""

    @staticmethod
    def _setup_connected(client: MCPClient) -> None:
        """Marca el cliente como conectado en memoria."""
        client._connected = True
        client._server_url = "http://localhost:3100"

    def test_refresh_tools_uses_server_ttl_ms(self, client: MCPClient) -> None:
        """_refresh_tools debe usar result._meta.ttlMs como TTL de caché."""
        import requests

        self._setup_connected(client)
        mock_response = _mock_response({
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "tools": [{"name": "read_file"}],
                "_meta": {"ttlMs": 5000, "cacheScope": "client"},
            },
        })
        with patch.object(requests, "post", return_value=mock_response):
            tools = client._refresh_tools()

        assert len(tools) == 1
        assert client._cache_ttl == 5.0  # 5000 ms -> 5 s

    def test_refresh_tools_default_ttl_without_meta(self, client: MCPClient) -> None:
        """Sin _meta.ttlMs el TTL debe permanecer en el default."""
        import requests

        self._setup_connected(client)
        mock_response = _mock_response({
            "jsonrpc": "2.0", "id": "1", "result": {"tools": [{"name": "read_file"}]},
        })
        with patch.object(requests, "post", return_value=mock_response):
            client._refresh_tools()

        assert client._cache_ttl == 60.0

    def test_list_tools_respects_server_ttl(self, client: MCPClient) -> None:
        """list_tools debe cachear por el TTL del servidor tras un refresh."""
        import requests

        self._setup_connected(client)
        mock_response = _mock_response({
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "tools": [{"name": "read_file"}],
                "_meta": {"ttlMs": 10000, "cacheScope": "client"},
            },
        })
        with patch.object(requests, "post", return_value=mock_response) as mock_post:
            first = client.list_tools(force_refresh=True)
            second = client.list_tools(force_refresh=False)

        assert first == second
        assert client._cache_ttl == 10.0
        # El segundo list_tools sale de caché: no hay nuevo POST
        assert mock_post.call_count == 1

    def test_list_tools_server_ttl_expires(self, client: MCPClient) -> None:
        """Cuando el TTL del servidor expira, list_tools debe refrescar."""
        import time

        import requests

        self._setup_connected(client)
        mock_response = _mock_response({
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "tools": [{"name": "read_file"}],
                "_meta": {"ttlMs": 2000, "cacheScope": "client"},
            },
        })
        with patch.object(requests, "post", return_value=mock_response) as mock_post:
            client.list_tools(force_refresh=True)
            # Envejecer la caché más allá del TTL del servidor (2 s)
            client._cache_ts = time.time() - 3.0
            client.list_tools(force_refresh=False)

        assert mock_post.call_count == 2


# ===========================================================================
# Tests: Headers Mcp-Method/Mcp-Name
# ===========================================================================


class TestMcpHeaders:
    """Tests de los headers Mcp-Method/Mcp-Name en requests JSON-RPC."""

    @staticmethod
    def _assert_mcp_headers(headers: dict, method: str) -> None:
        """Verifica que los headers MCP estén presentes y correctos."""
        assert headers[HEADER_METHOD] == method
        assert headers[HEADER_NAME] == "harness-mcp-client"

    def test_connect_legacy_sends_mcp_headers(self) -> None:
        """connect() legacy debe enviar headers Mcp-Method/Mcp-Name."""
        import requests

        mock_init = _mock_response({
            "jsonrpc": "2.0",
            "id": "1",
            "result": {"serverInfo": {"name": "s"}, "capabilities": {}},
        })
        mock_tools = _mock_response({"jsonrpc": "2.0", "id": "2", "result": {"tools": []}})
        with patch.object(requests, "post", side_effect=[mock_init, mock_tools]) as mock_post:
            c = MCPClient()
            c.connect("http://localhost:3100")

        self._assert_mcp_headers(mock_post.call_args_list[0][1]["headers"], "initialize")
        self._assert_mcp_headers(mock_post.call_args_list[1][1]["headers"], "tools/list")

    def test_connect_stateless_sends_mcp_headers(self) -> None:
        """connect_stateless debe enviar headers Mcp-Method/Mcp-Name."""
        import requests

        mock_response = _mock_response({"jsonrpc": "2.0", "id": "1", "result": {}})
        with patch.object(requests, "post", return_value=mock_response) as mock_post:
            c = MCPClient()
            c.connect_stateless("http://localhost:3100")

        self._assert_mcp_headers(mock_post.call_args[1]["headers"], STATELESS_DISCOVER_RPC)

    def test_execute_tool_sends_mcp_headers(self) -> None:
        """execute_tool debe enviar headers Mcp-Method/Mcp-Name."""
        import requests

        client = MCPClient()
        client._connected = True
        client._server_url = "http://localhost:3100"
        mock_response = _mock_response({
            "jsonrpc": "2.0",
            "id": "1",
            "result": {"content": [{"type": "text", "text": "ok"}], "isError": False},
        })
        with patch.object(requests, "post", return_value=mock_response) as mock_post:
            client.execute_tool("read_file", {})

        self._assert_mcp_headers(mock_post.call_args[1]["headers"], "tools/call")

    def test_disconnect_sends_mcp_headers(self) -> None:
        """disconnect debe enviar headers Mcp-Method/Mcp-Name."""
        import requests

        client = MCPClient()
        client._connected = True
        client._server_url = "http://localhost:3100"
        with patch.object(requests, "post", return_value=MagicMock()) as mock_post:
            client.disconnect()

        self._assert_mcp_headers(mock_post.call_args[1]["headers"], "shutdown")


# ===========================================================================
# Tests: Requests self-describing en modo stateless
# ===========================================================================


class TestStatelessSelfDescribing:
    """Tests de requests self-describing tras conectar en modo stateless."""

    def test_stateless_list_tools_includes_meta(self) -> None:
        """Tras conectar stateless, tools/list debe incluir _meta."""
        import requests

        mock_discover = _mock_response({"jsonrpc": "2.0", "id": "1", "result": {}})
        mock_tools = _mock_response({
            "jsonrpc": "2.0", "id": "2", "result": {"tools": [{"name": "read_file"}]},
        })
        with patch.object(requests, "post", side_effect=[mock_discover, mock_tools]) as mock_post:
            c = MCPClient()
            c.connect_stateless("http://localhost:3100")
            c.list_tools(force_refresh=True)

        tools_payload = mock_post.call_args_list[1][1]["json"]
        assert tools_payload["method"] == "tools/list"
        assert tools_payload["params"]["_meta"]["protocolVersion"] == "2026-07-28"

    def test_stateless_execute_tool_includes_meta(self) -> None:
        """Tras conectar stateless, tools/call debe incluir _meta."""
        import requests

        mock_discover = _mock_response({"jsonrpc": "2.0", "id": "1", "result": {}})
        mock_call = _mock_response({
            "jsonrpc": "2.0",
            "id": "2",
            "result": {"content": [{"type": "text", "text": "ok"}], "isError": False},
        })
        with patch.object(requests, "post", side_effect=[mock_discover, mock_call]) as mock_post:
            c = MCPClient()
            c.connect_stateless("http://localhost:3100")
            c.execute_tool("read_file", {})

        call_payload = mock_post.call_args_list[1][1]["json"]
        assert call_payload["method"] == "tools/call"
        assert "_meta" in call_payload["params"]
