"""
Smoke test del cableado del registry MCP con packages/tools REALES.

Valida que ``harness/tools_sandbox/mcp_servers.yaml`` declara los 11 servers
(5 oficiales + 4 de RE: rea/rc_devtools/ghidra_mcp/radare2 + serena y context7) con
transporte ``stdio`` coherente, comando/args no vacíos, env requeridas
documentadas y los nombres de tools REALES de cada paquete (NO los inventados
del cableado previo tipo ``get_repo``/``store_memory``).

Sin red: ningún server está habilitado, por lo que ``load_servers`` no abre
conexiones (los stdio se lanzarían solo al habilitarlos).

Fuentes de los nombres de tools (verificadas por web research):
  - filesystem: https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem
  - github:     https://github.com/github/github-mcp-server (npm @modelcontextprotocol/server-github DEPRECADO)
  - postgres:   https://github.com/modelcontextprotocol/servers-archived/tree/main/src/postgres (tool única: query)
  - memory:     https://github.com/modelcontextprotocol/servers/tree/main/src/memory
  - brave_search: https://github.com/brave/brave-search-mcp-server (reemplaza al archivado de modelcontextprotocol)
  - serena:     https://oraios.github.io/serena/01-about/035_tools.html (activate_project/get_current_config; NO activate_server/get_configuration)
  - context7:   https://github.com/upstash/context7/blob/master/packages/mcp/README.md (get-library-docs RENOMBRADO a query-docs)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.tools_sandbox.mcp_manager import MCPManager

# Ruta del YAML real versionado en el repo.
_REAL_YAML = Path(__file__).resolve().parents[1] / "tools_sandbox" / "mcp_servers.yaml"

# Los 5 servers oficiales que deben quedar cableados como stdio.
_OFFICIAL_SERVERS = ("filesystem", "github", "postgres", "memory", "brave_search")

# Los 2 servers de comprensión de código añadidos en esta iteración.
_COMPREHENSION_SERVERS = ("serena", "context7")

# Los servers de reverse engineering (filosofia REA: la herramienta correcta).
_RE_SERVERS = ("rea", "rc_devtools", "ghidra_mcp", "radare2")

# Servers de proposito general anexados (variados: web, browser, datos, git, docs).
_TOOLING_SERVERS = (
    "fetch", "time", "git", "sequentialthinking",
    "playwright", "firecrawl", "notion", "kubernetes",
)

# Servers frontera anexados (2026-10-14): browser/debug, observabilidad, DB/BaaS, cloud browser.
_FRONTIER_SERVERS = ("chrome_devtools", "sentry", "supabase", "browserbase")

# Packages reales (substring presente en args) por server.
_EXPECTED_PACKAGE = {
    "filesystem": "@modelcontextprotocol/server-filesystem",
    "github": "ghcr.io/github/github-mcp-server",
    "postgres": "@modelcontextprotocol/server-postgres",
    "memory": "@modelcontextprotocol/server-memory",
    "brave_search": "@brave/brave-search-mcp-server",
    "serena": "git+https://github.com/oraios/serena",
    "context7": "@upstash/context7-mcp",
}

# Tools REALES representativas que DEBEN estar declaradas por server.
_EXPECTED_TOOLS = {
    "filesystem": {"read_text_file", "write_file", "list_directory", "list_allowed_directories"},
    "github": {"get_file_contents", "create_pull_request", "search_repositories", "list_issues"},
    "postgres": {"query"},
    "memory": {"create_entities", "create_relations", "search_nodes", "read_graph"},
    "brave_search": {"brave_web_search", "brave_news_search", "brave_local_search"},
    "serena": {
        "find_symbol",
        "get_symbols_overview",
        "find_referencing_symbols",
        "find_declaration",
        "find_implementations",
        "get_diagnostics_for_file",
        "search_for_pattern",
        "replace_content",
        "activate_project",
        "get_current_config",
    },
    "context7": {"resolve-library-id", "query-docs"},
}

# Tools INVENTADAS del cableado previo que NO deben reaparecer.
_INVENTED_TOOLS = {"get_repo", "store_memory", "recall_memory", "web_fetch", "list_tables"}


@pytest.fixture
def manager() -> MCPManager:
    """Manager cargado desde el YAML real (ningún server habilitado)."""
    m = MCPManager()
    loaded = m.load_servers(str(_REAL_YAML))
    assert loaded > 0
    return m


class TestRegistryLoads:
    """El YAML real carga con MCPManager sin romperse."""

    def test_load_returns_servers(self, manager: MCPManager) -> None:
        """load_servers registra todos los servers del registry."""
        for name in (
            *_OFFICIAL_SERVERS, *_RE_SERVERS, *_TOOLING_SERVERS,
            *_FRONTIER_SERVERS, *_COMPREHENSION_SERVERS,
        ):
            assert name in manager._servers, f"falta server '{name}'"

    def test_load_returns_all_servers(self, manager: MCPManager) -> None:
        """El registry cableado completo declara exactamente 23 servers."""
        assert len(manager._servers) == 23, (
            f"esperados 23 servers, hay {len(manager._servers)}: "
            f"{sorted(manager._servers)}"
        )

    def test_no_enabled_means_no_network(self, manager: MCPManager) -> None:
        """Todo deshabilitado ⇒ cero conexiones (sin red)."""
        assert manager.get_connected_servers() == []


class TestStdioCoherence:
    """Todo server declara endpoint coherente con su transporte."""

    def test_stdio_has_command_and_args(self, manager: MCPManager) -> None:
        """Cada server stdio tiene command no vacío y args no vacíos."""
        for cfg in manager._servers.values():
            if cfg.is_stdio():
                assert cfg.command.strip(), f"'{cfg.name}': command vacío"
                assert cfg.args, f"'{cfg.name}': args vacíos"
                assert cfg.url == "", f"'{cfg.name}': stdio no debe tener url"

    def test_http_servers_have_url(self, manager: MCPManager) -> None:
        """Los servers http (si quedan) tienen url no vacía."""
        for cfg in manager._servers.values():
            if not cfg.is_stdio():
                assert cfg.url.strip(), f"'{cfg.name}': url vacía"

    def test_all_servers_have_tools(self, manager: MCPManager) -> None:
        """Ningún server se declara sin tools (lista no vacía)."""
        for cfg in manager._servers.values():
            assert cfg.tools, f"'{cfg.name}': sin tools declaradas"


class TestOfficialServersWiring:
    """Cada server oficial usa el package real, stdio y deshabilitado."""

    @pytest.mark.parametrize("name", _OFFICIAL_SERVERS)
    def test_transport_is_stdio(self, manager: MCPManager, name: str) -> None:
        """Los 5 oficiales usan transporte stdio (subproceso), no http falso."""
        cfg = manager._servers[name]
        assert cfg.is_stdio() is True
        assert cfg.transport == "stdio"

    @pytest.mark.parametrize("name", _OFFICIAL_SERVERS)
    def test_uses_real_package(self, manager: MCPManager, name: str) -> None:
        """El command/args referencia el package REAL verificado."""
        cfg = manager._servers[name]
        assert cfg.command in {"npx", "docker"}
        assert _EXPECTED_PACKAGE[name] in cfg.args

    @pytest.mark.parametrize("name", _OFFICIAL_SERVERS)
    def test_disabled_by_default(self, manager: MCPManager, name: str) -> None:
        """Los oficiales llegan deshabilitados (el usuario habilita)."""
        assert manager._servers[name].enabled is False

    @pytest.mark.parametrize("name", _OFFICIAL_SERVERS)
    def test_real_tools_present(self, manager: MCPManager, name: str) -> None:
        """Las tools REALES verificadas están declaradas."""
        tools = set(manager._servers[name].tools)
        missing = _EXPECTED_TOOLS[name] - tools
        assert not missing, f"'{name}': faltan tools reales {missing}"

    def test_no_invented_tools(self, manager: MCPManager) -> None:
        """No deben reaparecer nombres de tools inventados en ningún server."""
        all_tools: set[str] = set()
        for cfg in manager._servers.values():
            all_tools |= set(cfg.tools)
        assert not (_INVENTED_TOOLS & all_tools), (
            f"tools inventadas presentes: {_INVENTED_TOOLS & all_tools}"
        )


class TestComprehensionServersWiring:
    """serena y context7 (comprensión de código) quedan bien cableados como stdio."""

    @pytest.mark.parametrize("name", _COMPREHENSION_SERVERS)
    def test_transport_is_stdio(self, manager: MCPManager, name: str) -> None:
        """Ambos usan transporte stdio (subproceso), no http."""
        cfg = manager._servers[name]
        assert cfg.is_stdio() is True
        assert cfg.transport == "stdio"
        assert cfg.url == ""

    @pytest.mark.parametrize("name", _COMPREHENSION_SERVERS)
    def test_command_not_empty(self, manager: MCPManager, name: str) -> None:
        """El comando del subproceso no está vacío (uvx para serena, npx para context7)."""
        cfg = manager._servers[name]
        assert cfg.command.strip(), f"'{name}': command vacío"

    @pytest.mark.parametrize("name", _COMPREHENSION_SERVERS)
    def test_args_not_empty(self, manager: MCPManager, name: str) -> None:
        """Los args del subproceso no están vacíos."""
        cfg = manager._servers[name]
        assert cfg.args, f"'{name}': args vacíos"

    @pytest.mark.parametrize("name", _COMPREHENSION_SERVERS)
    def test_tools_not_empty(self, manager: MCPManager, name: str) -> None:
        """Cada server declara al menos una tool."""
        cfg = manager._servers[name]
        assert cfg.tools, f"'{name}': sin tools declaradas"

    @pytest.mark.parametrize("name", _COMPREHENSION_SERVERS)
    def test_uses_real_package(self, manager: MCPManager, name: str) -> None:
        """El command/args referencia el package REAL verificado."""
        cfg = manager._servers[name]
        assert _EXPECTED_PACKAGE[name] in cfg.args

    @pytest.mark.parametrize("name", _COMPREHENSION_SERVERS)
    def test_disabled_by_default(self, manager: MCPManager, name: str) -> None:
        """Llegan deshabilitados (el usuario los habilita)."""
        assert manager._servers[name].enabled is False

    @pytest.mark.parametrize("name", _COMPREHENSION_SERVERS)
    def test_real_tools_present(self, manager: MCPManager, name: str) -> None:
        """Las tools REALES verificadas están declaradas."""
        tools = set(manager._servers[name].tools)
        missing = _EXPECTED_TOOLS[name] - tools
        assert not missing, f"'{name}': faltan tools reales {missing}"

    def test_serena_uses_verified_config_tools(self, manager: MCPManager) -> None:
        """serena usa activate_project/get_current_config (NO los inventados)."""
        tools = set(manager._servers["serena"].tools)
        assert "activate_project" in tools
        assert "get_current_config" in tools
        assert "activate_server" not in tools
        assert "get_configuration" not in tools

    def test_context7_uses_renamed_query_docs(self, manager: MCPManager) -> None:
        """context7 usa query-docs (get-library-docs fue renombrado)."""
        tools = set(manager._servers["context7"].tools)
        assert "query-docs" in tools
        assert "resolve-library-id" in tools
        assert "get-library-docs" not in tools


class TestRequiredEnv:
    """Los servers que exigen credenciales documentan su env key."""

    @pytest.mark.parametrize(
        ("name", "env_key"),
        [
            ("github", "GITHUB_PERSONAL_ACCESS_TOKEN"),
            ("brave_search", "BRAVE_API_KEY"),
        ],
    )
    def test_env_key_present(self, manager: MCPManager, name: str, env_key: str) -> None:
        """github/brave_search declaran su variable de entorno requerida."""
        assert env_key in manager._servers[name].env


class TestMutationGuard:
    """Si se vacía command/args/tools el test debe fallar (mutation guard)."""

    def test_manager_rejects_stdio_without_command(self) -> None:
        """Un stdio sin command no puede registrarse (invariante del manager)."""
        from harness.tools_sandbox.mcp_manager import MCPConfigError

        with pytest.raises(MCPConfigError):
            MCPManager().register_server("x", transport="stdio", command="")
