"""
Tests del transporte dual (http + stdio) de la configuración MCP.

Cubre la integración de REA (morluto/rea, MCP server stdio) en el harness:

(a) ``MCPServerConfig`` http (url) sigue válido — backward-compat total.
(b) ``MCPServerConfig`` stdio válido (command + args).
(c) stdio sin ``command`` → error tipado (``MCPConfigError``/``ValueError``)
    con WHAT+WHY+WHERE.
(d) http sin ``url`` → error tipado.
(e) ``MCPManager.load_servers`` parsea el YAML real (incluye ``rea`` stdio) sin
    romper los servers http existentes.
(f) ``is_stdio()`` correcto en ambos transportes.
(g) Mutation: si se elimina la validación de ``command`` el test falla.

Sin red: todos los servidores están deshabilitados en el YAML real y el
lanzamiento stdio se prueba con un runner inyectado (DI).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from harness.tools_sandbox import mcp_manager as mcp_manager_module
from harness.tools_sandbox.mcp_client import MCPClient
from harness.tools_sandbox.mcp_manager import (
    MCPConfigError,
    MCPManager,
    MCPServerConfig,
)

# Ruta del YAML real versionado en el repo.
_REAL_YAML = Path(__file__).resolve().parents[1] / "tools_sandbox" / "mcp_servers.yaml"


# ===========================================================================
# (a) HTTP — backward-compat
# ===========================================================================


class TestHTTPConfigBackwardCompat:
    """El transporte http (url) debe seguir funcionando sin cambios."""

    def test_http_url_valid(self) -> None:
        """Un config http con url es válido y transport por defecto es http."""
        cfg = MCPServerConfig(name="filesystem", url="http://localhost:3100")
        assert cfg.name == "filesystem"
        assert cfg.url == "http://localhost:3100"
        assert cfg.transport == "http"
        assert cfg.is_stdio() is False

    def test_http_positional_backward_compat(self) -> None:
        """La construcción posicional (name, url) sigue soportada."""
        cfg = MCPServerConfig("github", "http://localhost:3101")
        assert cfg.url == "http://localhost:3101"
        assert cfg.transport == "http"

    def test_http_defaults_unchanged(self) -> None:
        """Los defaults http no cambian (tools, enabled, install_hint...)."""
        cfg = MCPServerConfig(name="test", url="http://localhost:9999")
        assert cfg.description == ""
        assert cfg.tools == []
        assert cfg.enabled is False
        assert cfg.install_hint == ""

    def test_http_explicit_transport(self) -> None:
        """transport='http' explícito con url es válido."""
        cfg = MCPServerConfig(name="s", url="http://x", transport="http")
        assert cfg.is_stdio() is False


# ===========================================================================
# (b) + (c) STDIO
# ===========================================================================


class TestStdioConfig:
    """Configuración stdio (command + args + env)."""

    def test_stdio_valid(self) -> None:
        """Un config stdio con command/args es válido."""
        cfg = MCPServerConfig(
            name="rea",
            transport="stdio",
            command="npx",
            args=["-y", "rea-agents@latest", "mcp"],
            env={"REA_ANALYSIS_PROVIDER": "ghidra"},
        )
        assert cfg.transport == "stdio"
        assert cfg.command == "npx"
        assert cfg.args == ["-y", "rea-agents@latest", "mcp"]
        assert cfg.env == {"REA_ANALYSIS_PROVIDER": "ghidra"}
        assert cfg.url == ""

    def test_stdio_without_command_raises(self) -> None:
        """(c) stdio sin command → MCPConfigError tipado (ValueError)."""
        with pytest.raises(MCPConfigError) as exc_info:
            MCPServerConfig(name="rea", transport="stdio")
        err = exc_info.value
        assert isinstance(err, ValueError)
        message = str(err)
        assert "WHAT:" in message
        assert "WHY:" in message
        assert "WHERE:" in message
        assert "command" in message
        assert "rea" in message

    def test_stdio_blank_command_raises(self) -> None:
        """Un command compuesto solo por espacios se considera ausente."""
        with pytest.raises(MCPConfigError):
            MCPServerConfig(name="rea", transport="stdio", command="   ")

    def test_unknown_transport_raises(self) -> None:
        """Un transporte desconocido → error tipado con WHAT/WHY/WHERE."""
        with pytest.raises(MCPConfigError) as exc_info:
            MCPServerConfig(name="weird", transport="sse", command="x")  # type: ignore[arg-type]
        message = str(exc_info.value)
        assert "WHAT:" in message and "WHY:" in message and "WHERE:" in message


# ===========================================================================
# (d) HTTP sin url
# ===========================================================================


class TestHTTPMissingUrl:
    """El transporte http exige url."""

    def test_http_without_url_raises(self) -> None:
        """(d) http sin url → MCPConfigError tipado (ValueError)."""
        with pytest.raises(MCPConfigError) as exc_info:
            MCPServerConfig(name="filesystem")
        err = exc_info.value
        assert isinstance(err, ValueError)
        message = str(err)
        assert "WHAT:" in message
        assert "WHY:" in message
        assert "WHERE:" in message
        assert "url" in message


# ===========================================================================
# (f) is_stdio()
# ===========================================================================


class TestIsStdio:
    """is_stdio() discrimina correctamente ambos transportes."""

    def test_is_stdio_true(self) -> None:
        """stdio → is_stdio() True."""
        cfg = MCPServerConfig(name="rea", transport="stdio", command="npx")
        assert cfg.is_stdio() is True

    def test_is_stdio_false_for_http(self) -> None:
        """http → is_stdio() False."""
        cfg = MCPServerConfig(name="fs", url="http://localhost:3100")
        assert cfg.is_stdio() is False


# ===========================================================================
# (e) load_servers con el YAML real
# ===========================================================================


class TestLoadServersRealYaml:
    """load_servers parsea el YAML real incluyendo REA (stdio)."""

    @pytest.fixture
    def manager(self) -> MCPManager:
        """Manager cargado desde el YAML real (ningún server habilitado)."""
        m = MCPManager()
        loaded = m.load_servers(str(_REAL_YAML))
        assert loaded > 0
        return m

    def test_rea_registered_as_stdio(self, manager: MCPManager) -> None:
        """REA se registra con transporte stdio, command npx y args de MCP."""
        assert "rea" in manager._servers
        rea = manager._servers["rea"]
        assert rea.is_stdio() is True
        assert rea.transport == "stdio"
        assert rea.command == "npx"
        assert rea.args == ["-y", "rea-agents@latest", "mcp"]
        assert rea.url == ""

    def test_rea_tools_present(self, manager: MCPManager) -> None:
        """REA expone las tools clave de ingeniería inversa."""
        rea = manager._servers["rea"]
        assert "analyze_function" in rea.tools
        assert "decompile" in rea.tools

    def test_rea_disabled_by_default(self, manager: MCPManager) -> None:
        """REA llega deshabilitado (el usuario lo habilita explícitamente)."""
        assert manager._servers["rea"].enabled is False

    def test_existing_http_servers_still_load(self, manager: MCPManager) -> None:
        """Los servers http existentes siguen cargando con su url."""
        assert "filesystem" in manager._servers
        fs = manager._servers["filesystem"]
        assert fs.is_stdio() is False
        assert fs.url == "http://localhost:3100"

    def test_all_registered_servers_have_valid_endpoint(
        self, manager: MCPManager
    ) -> None:
        """Todo server del YAML tiene endpoint coherente con su transporte."""
        for cfg in manager._servers.values():
            if cfg.is_stdio():
                assert cfg.command
            else:
                assert cfg.url

    def test_no_enabled_server_means_no_connection(
        self, manager: MCPManager
    ) -> None:
        """Sin servers habilitados no se abre ninguna conexión (sin red)."""
        assert manager.get_connected_servers() == []


# ===========================================================================
# register_server + connect_all dispatch (stdio)
# ===========================================================================


class TestRegisterAndConnectStdio:
    """register_server/connect_all operan con transporte stdio."""

    def test_register_server_stdio(self) -> None:
        """register_server acepta transport stdio + command/args/env."""
        m = MCPManager()
        m.register_server(
            "rea",
            transport="stdio",
            command="npx",
            args=["-y", "rea-agents@latest", "mcp"],
            env={"REA_ANALYSIS_PROVIDER": "hopper"},
            enabled=True,
        )
        cfg = m._servers["rea"]
        assert cfg.is_stdio() is True
        assert cfg.command == "npx"
        assert cfg.env["REA_ANALYSIS_PROVIDER"] == "hopper"

    def test_connect_all_dispatches_stdio(self) -> None:
        """connect_all llama connect_stdio (no connect http) para stdio."""
        m = MCPManager()
        m.register_server(
            "rea",
            transport="stdio",
            command="npx",
            args=["-y", "rea-agents@latest", "mcp"],
            env={"REA_ANALYSIS_PROVIDER": "ghidra"},
            enabled=True,
        )
        with patch.object(mcp_manager_module, "MCPClient") as mock_cls:
            instance = mock_cls.return_value
            instance.is_connected.return_value = False
            instance.connect_stdio.return_value = True

            connected = m.connect_all()

            assert connected == 1
            instance.connect_stdio.assert_called_once_with(
                "npx",
                ["-y", "rea-agents@latest", "mcp"],
                {"REA_ANALYSIS_PROVIDER": "ghidra"},
            )
            instance.connect.assert_not_called()

    def test_connect_all_dispatches_http(self) -> None:
        """connect_all sigue usando connect(url) para http."""
        m = MCPManager()
        m.register_server("fs", "http://localhost:3100", enabled=True)
        with patch.object(mcp_manager_module, "MCPClient") as mock_cls:
            instance = mock_cls.return_value
            instance.is_connected.return_value = False
            instance.connect.return_value = True

            connected = m.connect_all()

            assert connected == 1
            instance.connect.assert_called_once_with("http://localhost:3100")
            instance.connect_stdio.assert_not_called()


# ===========================================================================
# Adapter stdio de MCPClient (DI del runner, sin red/procesos reales)
# ===========================================================================


class TestClientStdioAdapter:
    """connect_stdio lanza el subproceso vía runner inyectado (DI)."""

    def test_connect_stdio_success(self) -> None:
        """connect_stdio lanza el subproceso y marca estado stdio."""
        fake_proc = MagicMock()
        runner = MagicMock(return_value=fake_proc)
        client = MCPClient()

        ok = client.connect_stdio(
            "npx",
            ["-y", "rea-agents@latest", "mcp"],
            runner=runner,
        )

        assert ok is True
        runner.assert_called_once()
        argv, kwargs = runner.call_args
        assert argv[0] == ["npx", "-y", "rea-agents@latest", "mcp"]
        assert kwargs["text"] is True
        assert client.is_connected() is True
        assert client._transport == "stdio"
        assert client._stdio_proc is fake_proc

    def test_connect_stdio_merges_env(self) -> None:
        """connect_stdio fusiona env extra sobre os.environ."""
        runner = MagicMock(return_value=MagicMock())
        client = MCPClient()

        client.connect_stdio(
            "npx",
            ["mcp"],
            env={"REA_ANALYSIS_PROVIDER": "ghidra"},
            runner=runner,
        )

        _, kwargs = runner.call_args
        assert kwargs["env"]["REA_ANALYSIS_PROVIDER"] == "ghidra"
        assert "PATH" in kwargs["env"] or "Path" in kwargs["env"]

    def test_connect_stdio_empty_command(self) -> None:
        """connect_stdio con command vacío retorna False y no lanza nada."""
        runner = MagicMock()
        client = MCPClient()

        assert client.connect_stdio("", runner=runner) is False
        runner.assert_not_called()
        assert client.is_connected() is False

    def test_connect_stdio_spawn_error(self) -> None:
        """connect_stdio captura OSError del runner y retorna False."""
        runner = MagicMock(side_effect=OSError("npx not found"))
        client = MCPClient()

        assert client.connect_stdio("npx", ["mcp"], runner=runner) is False
        assert client.is_connected() is False

    def test_disconnect_terminates_stdio(self) -> None:
        """disconnect termina el subproceso stdio."""
        fake_proc = MagicMock()
        runner = MagicMock(return_value=fake_proc)
        client = MCPClient()
        client.connect_stdio("npx", ["mcp"], runner=runner)

        client.disconnect()

        fake_proc.terminate.assert_called_once()
        assert client._stdio_proc is None
        assert client.is_connected() is False


# ===========================================================================
# (g) Mutation guard
# ===========================================================================


class TestMutationGuard:
    """Si se elimina la validación de command, estos tests fallan."""

    def test_mutation_command_validation_required(self) -> None:
        """(g) stdio sin command DEBE lanzar: sin validación, test rojo."""
        with pytest.raises(ValueError):
            MCPServerConfig(name="rea", transport="stdio", command="")

    def test_mutation_url_validation_required(self) -> None:
        """Simétrico: http sin url DEBE lanzar (mutation guard)."""
        with pytest.raises(ValueError):
            MCPServerConfig(name="fs", transport="http", url="")
