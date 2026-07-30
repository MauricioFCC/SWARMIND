"""
Tests para MCPClient — cobertura completa de mcp_client.py.

Cubre:
- Inicialización del cliente
- Conexión/sesión (connect, disconnect, is_connected)
- Descubrimiento de herramientas (list_tools, _refresh_tools, caché)
- Ejecución de herramientas (execute_tool)
- Manejo de errores (timeout, conexión rechazada, ImportError)
- Edge cases (caché, TTL, cliente no conectado)
"""
from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from harness.tools_sandbox.mcp_client import (
    DEFAULT_TIMEOUT,
    MCPClient,
    MCPConnectionError,
    MCPResult,
    MCPTimeoutError,
    MCPTool,
    MCPToolError,
)

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def client() -> MCPClient:
    """Fixture: MCPClient con valores por defecto."""
    return MCPClient()


# ===========================================================================
# Tests: Inicialización
# ===========================================================================


class TestInit:
    """Tests de inicialización del MCPClient."""

    def test_default_timeout(self) -> None:
        """Debe usar DEFAULT_TIMEOUT (30) por defecto."""
        c = MCPClient()
        assert c._default_timeout == DEFAULT_TIMEOUT

    def test_custom_timeout(self) -> None:
        """Debe aceptar timeout personalizado."""
        c = MCPClient(default_timeout=15)
        assert c._default_timeout == 15

    def test_initial_state_not_connected(self) -> None:
        """Debe comenzar desconectado."""
        c = MCPClient()
        assert c._server_url is None
        assert c._connected is False
        assert c._tools_cache == []
        assert c._cache_ts == 0.0
        assert c._cache_ttl == 60.0

    def test_is_connected_returns_false_initially(self) -> None:
        """is_connected() debe retornar False al inicio."""
        c = MCPClient()
        assert c.is_connected() is False

    def test_set_cache_ttl(self) -> None:
        """set_cache_ttl debe actualizar el TTL con piso 1.0."""
        c = MCPClient()
        c.set_cache_ttl(30.0)
        assert c._cache_ttl == 30.0

    def test_set_cache_ttl_minimum(self) -> None:
        """set_cache_ttl debe aplicar piso de 1.0 segundo."""
        c = MCPClient()
        c.set_cache_ttl(0.5)
        assert c._cache_ttl == 1.0

    def test_clear_cache(self) -> None:
        """clear_cache debe vaciar la caché y resetear timestamp."""
        c = MCPClient()
        c._tools_cache = [MCPTool(name="test")]
        c._cache_ts = 12345.0
        c.clear_cache()
        assert c._tools_cache == []
        assert c._cache_ts == 0.0


# ===========================================================================
# Tests: Conexión
# ===========================================================================


class TestConnect:
    """Tests del método connect()."""

    def _make_mock_response(self, json_data: dict) -> MagicMock:
        """Crea un mock de respuesta HTTP."""
        m = MagicMock()
        m.json.return_value = json_data
        return m

    def test_connect_success(self) -> None:
        """connect exitoso debe establecer conexión y cargar tools."""
        import requests
        mock_response = self._make_mock_response({
            "jsonrpc": "2.0",
            "id": "1",
            "result": {"serverInfo": {"name": "test-server"}, "capabilities": {}},
        })
        with patch.object(requests, "post", return_value=mock_response) as mock_post:
            # El connect hace POST de initialize y luego de tools/list
            # Necesitamos que tools/list también responda
            mock_response2 = MagicMock()
            mock_response2.json.return_value = {
                "jsonrpc": "2.0", "id": "2",
                "result": {"tools": []},
            }
            # Segundo llamado
            mock_post.side_effect = [mock_response, mock_response2]

            c = MCPClient()
            result = c.connect("http://localhost:3100")

            assert result is True
            assert c._connected is True
            assert c._server_url == "http://localhost:3100"
            assert mock_post.call_count >= 2
            payload = mock_post.call_args_list[0][1]["json"]
            assert payload["method"] == "initialize"

    def test_connect_trailing_slash(self) -> None:
        """connect debe eliminar trailing slash de la URL."""
        import requests
        mock_response = self._make_mock_response({
            "jsonrpc": "2.0", "id": "1",
            "result": {"serverInfo": {"name": "s"}},
        })
        mock_response2 = MagicMock()
        mock_response2.json.return_value = {
            "jsonrpc": "2.0", "id": "2",
            "result": {"tools": []},
        }
        with patch.object(requests, "post", side_effect=[mock_response, mock_response2]):
            c = MCPClient()
            c.connect("http://localhost:3100/")
            assert c._server_url == "http://localhost:3100"

    def test_connect_error_in_response(self) -> None:
        """connect debe retornar False si el server devuelve error."""
        import requests
        mock_response = self._make_mock_response({
            "jsonrpc": "2.0", "id": "1",
            "error": {"code": -32000, "message": "Server error"},
        })
        with patch.object(requests, "post", return_value=mock_response):
            c = MCPClient()
            result = c.connect("http://localhost:3100")
            assert result is False
            assert c._connected is False
            assert c._server_url is None

    def test_connect_http_error(self) -> None:
        """connect debe retornar False si hay HTTP error."""
        import requests
        with patch.object(requests, "post", side_effect=Exception("Connection refused")):
            c = MCPClient()
            result = c.connect("http://localhost:3100")
            assert result is False
            assert c._connected is False

    def test_connect_raise_for_status(self) -> None:
        """connect debe retornar False si raise_for_status() lanza error."""
        import requests
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")
        with patch.object(requests, "post", return_value=mock_response):
            c = MCPClient()
            result = c.connect("http://localhost:3100")
            assert result is False

    def test_connect_import_error(self) -> None:
        """connect debe retornar False si requests no está instalado."""
        # Forzar ImportError al importar requests dentro de connect()
        # Primero removemos requests de sys.modules para que __import__ se ejecute
        import builtins

        original_import = builtins.__import__
        had_requests = "requests" in sys.modules
        if had_requests:
            del sys.modules["requests"]

        def mock_import(name, *args, **kwargs):
            if name == "requests":
                raise ImportError("No module named 'requests'")
            return original_import(name, *args, **kwargs)

        try:
            with patch("builtins.__import__", side_effect=mock_import):
                c = MCPClient()
                result = c.connect("http://localhost:3100")
                assert result is False
                assert c._connected is False
        finally:
            # Restaurar
            if had_requests:
                import requests as _req
                sys.modules["requests"] = _req

    def test_connect_custom_timeout(self) -> None:
        """connect debe usar timeout personalizado si se pasa."""
        import requests
        mock_response = self._make_mock_response({
            "jsonrpc": "2.0", "id": "1",
            "result": {"serverInfo": {"name": "s"}},
        })
        mock_response2 = MagicMock()
        mock_response2.json.return_value = {
            "jsonrpc": "2.0", "id": "2",
            "result": {"tools": []},
        }
        with patch.object(requests, "post", side_effect=[mock_response, mock_response2]) as mock_post:
            c = MCPClient(default_timeout=30)
            c.connect("http://localhost:3100", timeout=10)
            # Primer llamado (initialize) debe usar timeout=10
            first_call_kwargs = mock_post.call_args_list[0][1]
            assert first_call_kwargs["timeout"] == 10


class TestDisconnect:
    """Tests del método disconnect()."""

    def test_disconnect_connected(self, client: MCPClient) -> None:
        """disconnect debe enviar shutdown y limpiar estado."""
        import requests
        # Simular conectado
        client._connected = True
        client._server_url = "http://localhost:3100"
        client._tools_cache = [MCPTool(name="test")]

        with patch.object(requests, "post", return_value=MagicMock()) as mock_post:
            client.disconnect()

        assert client._connected is False
        assert client._server_url is None
        assert client._tools_cache == []
        mock_post.assert_called_once()

    def test_disconnect_not_connected(self, client: MCPClient) -> None:
        """disconnect sin conexión no debe hacer nada."""
        import requests
        client._connected = False
        client._server_url = None

        with patch.object(requests, "post") as mock_post:
            client.disconnect()
            mock_post.assert_not_called()

    def test_disconnect_best_effort(self, client: MCPClient) -> None:
        """disconnect debe ignorar errores del shutdown (best-effort)."""
        import requests
        client._connected = True
        client._server_url = "http://localhost:3100"

        with patch.object(requests, "post", side_effect=Exception("Network error")):
            # No debe lanzar excepción
            client.disconnect()
            assert client._connected is False
            assert client._server_url is None


class TestIsConnected:
    """Tests de is_connected()."""

    def test_is_connected_true(self, client: MCPClient) -> None:
        """is_connected debe retornar True si está conectado."""
        client._connected = True
        assert client.is_connected() is True

    def test_is_connected_false(self, client: MCPClient) -> None:
        """is_connected debe retornar False si no está conectado."""
        client._connected = False
        assert client.is_connected() is False


# ===========================================================================
# Tests: List Tools
# ===========================================================================


class TestListTools:
    """Tests del método list_tools()."""

    def test_list_tools_not_connected(self, client: MCPClient) -> None:
        """list_tools sin conexión debe retornar lista vacía."""
        result = client.list_tools()
        assert result == []

    def test_list_tools_cached(self, client: MCPClient) -> None:
        """list_tools debe retornar caché si es válida."""
        client._connected = True
        client._server_url = "http://localhost:3100"
        cached_tools = [MCPTool(name="cached_tool")]
        client._tools_cache = cached_tools
        client._cache_ts = time.time()

        result = client.list_tools(force_refresh=False)
        assert result == cached_tools

    def test_list_tools_cache_expired(self, client: MCPClient) -> None:
        """list_tools debe refrescar si caché expiró."""
        client._connected = True
        client._server_url = "http://localhost:3100"
        cached_tools = [MCPTool(name="old_tool")]
        client._tools_cache = cached_tools
        client._cache_ts = time.time() - 120.0  # Expiró

        with patch.object(client, "_refresh_tools", return_value=[MCPTool(name="fresh_tool")]) as mock_refresh:
            result = client.list_tools()
            mock_refresh.assert_called_once()
            assert result == [MCPTool(name="fresh_tool")]

    def test_list_tools_force_refresh(self, client: MCPClient) -> None:
        """list_tools con force_refresh=True debe ignorar caché."""
        client._connected = True
        client._server_url = "http://localhost:3100"
        client._tools_cache = [MCPTool(name="cached")]
        client._cache_ts = time.time()

        with patch.object(client, "_refresh_tools", return_value=[MCPTool(name="fresh")]) as mock_refresh:
            result = client.list_tools(force_refresh=True)
            mock_refresh.assert_called_once()
            assert result == [MCPTool(name="fresh")]


class TestRefreshTools:
    """Tests del método _refresh_tools()."""

    def test_refresh_no_server_url(self, client: MCPClient) -> None:
        """_refresh_tools sin server_url debe retornar lista vacía."""
        client._server_url = None
        result = client._refresh_tools()
        assert result == []

    def test_refresh_success(self, client: MCPClient) -> None:
        """_refresh_tools exitoso debe poblar la caché."""
        import requests
        client._server_url = "http://localhost:3100"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0", "id": "1",
            "result": {
                "tools": [
                    {"name": "read_file", "description": "Read a file", "inputSchema": {"type": "object"}},
                ],
            },
        }
        with patch.object(requests, "post", return_value=mock_response):
            tools = client._refresh_tools()
            assert len(tools) == 1
            assert tools[0].name == "read_file"
            assert tools[0].description == "Read a file"
            assert tools[0].input_schema == {"type": "object"}
            assert tools[0].server_name == "http://localhost:3100"
            assert len(client._tools_cache) == 1
            assert client._cache_ts > 0

    def test_refresh_error_response(self, client: MCPClient) -> None:
        """_refresh_tools con error en respuesta debe retornar lista vacía."""
        import requests
        client._server_url = "http://localhost:3100"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0", "id": "1",
            "error": {"code": -32601, "message": "Method not found"},
        }
        with patch.object(requests, "post", return_value=mock_response):
            tools = client._refresh_tools()
            assert tools == []

    def test_refresh_exception(self, client: MCPClient) -> None:
        """_refresh_tools con excepción debe retornar lista vacía."""
        import requests
        client._server_url = "http://localhost:3100"
        with patch.object(requests, "post", side_effect=Exception("Timeout")):
            tools = client._refresh_tools()
            assert tools == []

    def test_refresh_missing_tools_key(self, client: MCPClient) -> None:
        """_refresh_tools sin 'tools' en respuesta debe retornar lista vacía."""
        import requests
        client._server_url = "http://localhost:3100"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0", "id": "1",
            "result": {},
        }
        with patch.object(requests, "post", return_value=mock_response):
            tools = client._refresh_tools()
            assert tools == []


# ===========================================================================
# Tests: Execute Tool
# ===========================================================================


class TestExecuteTool:
    """Tests del método execute_tool()."""

    def test_execute_not_connected(self, client: MCPClient) -> None:
        """execute_tool sin conexión debe retornar MCPResult con error."""
        result = client.execute_tool("read_file", {"path": "/tmp/test.txt"})
        assert result.success is False
        assert result.error == "Not connected to MCP server"
        assert result.tool_name == "read_file"
        assert result.server_name == ""
        assert result.duration_ms >= 0

    def test_execute_success_text_content(self, client: MCPClient) -> None:
        """execute_tool exitoso con contenido de texto."""
        import requests
        client._connected = True
        client._server_url = "http://localhost:3100"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0", "id": "1",
            "result": {
                "content": [{"type": "text", "text": "File content here"}],
                "isError": False,
            },
        }
        with patch.object(requests, "post", return_value=mock_response):
            result = client.execute_tool("read_file", {"path": "/tmp/test.txt"})
            assert result.success is True
            assert result.output == "File content here"
            assert result.tool_name == "read_file"
            assert result.server_name == "http://localhost:3100"
            assert result.duration_ms >= 0
            assert result.error is None

    def test_execute_no_text_content_fallback(self, client: MCPClient) -> None:
        """execute_tool debe usar content completo si no hay tipo 'text'."""
        import requests
        client._connected = True
        client._server_url = "http://localhost:3100"

        mock_response = MagicMock()
        content_array = [{"type": "image", "data": "base64..."}]
        mock_response.json.return_value = {
            "jsonrpc": "2.0", "id": "1",
            "result": {"content": content_array, "isError": False},
        }
        with patch.object(requests, "post", return_value=mock_response):
            result = client.execute_tool("get_image", {})
            assert result.success is True
            assert result.output == content_array  # fallback

    def test_execute_empty_content(self, client: MCPClient) -> None:
        """execute_tool con content vacío debe tener output None."""
        import requests
        client._connected = True
        client._server_url = "http://localhost:3100"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0", "id": "1",
            "result": {"content": [], "isError": False},
        }
        with patch.object(requests, "post", return_value=mock_response):
            result = client.execute_tool("empty_tool", {})
            assert result.success is True
            assert result.output is None

    def test_execute_is_error_true(self, client: MCPClient) -> None:
        """execute_tool con isError=True debe marcar success=False."""
        import requests
        client._connected = True
        client._server_url = "http://localhost:3100"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0", "id": "1",
            "result": {
                "content": [{"type": "text", "text": "Error occurred"}],
                "isError": True,
            },
        }
        with patch.object(requests, "post", return_value=mock_response):
            result = client.execute_tool("faulty", {})
            assert result.success is False
            assert result.error == "Tool returned error"
            assert result.output == "Error occurred"

    def test_execute_error_in_response(self, client: MCPClient) -> None:
        """execute_tool con error en respuesta JSON-RPC."""
        import requests
        client._connected = True
        client._server_url = "http://localhost:3100"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0", "id": "1",
            "error": {"code": -32603, "message": "Internal error"},
        }
        with patch.object(requests, "post", return_value=mock_response):
            result = client.execute_tool("faulty", {})
            assert result.success is False
            assert result.error is not None

    def test_execute_exception(self, client: MCPClient) -> None:
        """execute_tool con excepción de red debe retornar MCPResult con error."""
        import requests
        client._connected = True
        client._server_url = "http://localhost:3100"

        with patch.object(requests, "post", side_effect=Exception("Connection timeout")):
            result = client.execute_tool("read_file", {"path": "/tmp/test.txt"})
            assert result.success is False
            assert "Connection timeout" in result.error
            assert result.duration_ms >= 0

    def test_execute_with_custom_timeout(self, client: MCPClient) -> None:
        """execute_tool debe usar timeout personalizado."""
        import requests
        client._connected = True
        client._server_url = "http://localhost:3100"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0", "id": "1",
            "result": {"content": [{"type": "text", "text": "ok"}], "isError": False},
        }
        with patch.object(requests, "post", return_value=mock_response) as mock_post:
            client.execute_tool("t", {}, timeout=5)
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["timeout"] == 5

    def test_execute_verify_request_id(self, client: MCPClient) -> None:
        """execute_tool debe pasar request_id al payload."""
        import requests
        client._connected = True
        client._server_url = "http://localhost:3100"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0", "id": "1",
            "result": {"content": [{"type": "text", "text": "ok"}], "isError": False},
        }
        with patch.object(requests, "post", return_value=mock_response) as mock_post:
            client.execute_tool("t", {})
            payload = mock_post.call_args[1]["json"]
            assert payload["method"] == "tools/call"
            assert payload["params"]["name"] == "t"
            assert payload["params"]["arguments"] == {}

    def test_execute_server_url_in_result(self, client: MCPClient) -> None:
        """execute_tool debe incluir server_name en MCPResult incluso si falla la conexion."""
        result = client.execute_tool("t", {})
        assert result.server_name == ""


# ===========================================================================
# Tests: _make_request
# ===========================================================================


class TestMakeRequest:
    """Tests del método _make_request()."""

    def test_make_request_defaults(self, client: MCPClient) -> None:
        """_make_request debe construir payload JSON-RPC 2.0."""
        payload = client._make_request("test_method", {"foo": "bar"})
        assert payload["jsonrpc"] == "2.0"
        assert payload["method"] == "test_method"
        assert payload["params"] == {"foo": "bar"}
        assert "id" in payload
        assert len(payload["id"]) == 12

    def test_make_request_custom_id(self, client: MCPClient) -> None:
        """_make_request debe aceptar request_id personalizado."""
        payload = client._make_request("method", {}, request_id="custom123")
        assert payload["id"] == "custom123"


# ===========================================================================
# Tests: Clases de error
# ===========================================================================


class TestExceptions:
    """Tests de las excepciones personalizadas."""

    def test_mcp_connection_error(self) -> None:
        """MCPConnectionError debe ser una Exception."""
        err = MCPConnectionError("connection failed")
        assert isinstance(err, Exception)
        assert str(err) == "connection failed"

    def test_mcp_tool_error(self) -> None:
        """MCPToolError debe ser una Exception."""
        err = MCPToolError("tool failed")
        assert isinstance(err, Exception)
        assert str(err) == "tool failed"

    def test_mcp_timeout_error(self) -> None:
        """MCPTimeoutError debe ser una Exception."""
        err = MCPTimeoutError("timeout")
        assert isinstance(err, Exception)
        assert str(err) == "timeout"


# ===========================================================================
# Tests: Dataclasses
# ===========================================================================


class TestMCPTool:
    """Tests de la dataclass MCPTool."""

    def test_defaults(self) -> None:
        """MCPTool debe tener valores por defecto."""
        tool = MCPTool(name="test")
        assert tool.name == "test"
        assert tool.description == ""
        assert tool.input_schema == {}
        assert tool.server_name == ""

    def test_full_init(self) -> None:
        """MCPTool debe aceptar todos los campos."""
        tool = MCPTool(
            name="read",
            description="Reads a file",
            input_schema={"type": "object"},
            server_name="server1",
        )
        assert tool.name == "read"
        assert tool.description == "Reads a file"
        assert tool.input_schema == {"type": "object"}
        assert tool.server_name == "server1"


class TestMCPResult:
    """Tests de la dataclass MCPResult."""

    def test_defaults(self) -> None:
        """MCPResult debe tener valores por defecto."""
        result = MCPResult(
            success=True,
            output="data",
            tool_name="t1",
            server_name="s1",
            duration_ms=10.5,
        )
        assert result.success is True
        assert result.output == "data"
        assert result.tool_name == "t1"
        assert result.server_name == "s1"
        assert result.duration_ms == 10.5
        assert result.error is None
        assert result.request_id == ""

    def test_full_init(self) -> None:
        """MCPResult debe aceptar todos los campos."""
        result = MCPResult(
            success=False,
            output=None,
            tool_name="t1",
            server_name="s1",
            duration_ms=5.0,
            error="Something went wrong",
            request_id="req-123",
        )
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.request_id == "req-123"
