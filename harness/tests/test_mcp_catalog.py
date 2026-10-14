"""Tests del catalogo MCP y del mapeo tarea -> herramientas (filosofia REA).

Garantizan que la seleccion de herramientas NUNCA inventa servers (todo nombre
devuelto existe en la SSOT) y que el mapeo por keyword cubre los casos clave.
"""

from __future__ import annotations

from harness.tools_sandbox.mcp_catalog import (
    TASK_SERVER_KEYWORDS,
    catalog_servers,
    servers_for_task,
)


class TestCatalog:
    """El catalogo carga la SSOT real."""

    def test_catalog_has_servers(self) -> None:
        names = catalog_servers()
        assert len(names) >= 20
        for expected in ("rea", "fetch", "time", "playwright", "chrome_devtools"):
            assert expected in names, expected

    def test_catalog_names_unique(self) -> None:
        names = catalog_servers()
        assert len(names) == len(set(names))


class TestServersForTask:
    """Seleccion por keyword; solo nombres reales del catalogo."""

    def test_reverse_engineering_task(self) -> None:
        tools = servers_for_task("haz ingenieria inversa del binario y decompila")
        assert "rea" in tools
        assert "ghidra_mcp" in tools

    def test_browser_task(self) -> None:
        tools = servers_for_task("abre el navegador y prueba el checkout con playwright")
        assert "playwright" in tools
        assert "chrome_devtools" in tools

    def test_scrape_task(self) -> None:
        assert "firecrawl" in servers_for_task("haz scraping de la web y extrae datos")

    def test_time_task(self) -> None:
        assert "time" in servers_for_task("que hora es en otra zona horaria")

    def test_empty_task_returns_nothing(self) -> None:
        assert servers_for_task("") == ()
        assert servers_for_task("   ") == ()

    def test_unknown_task_returns_nothing(self) -> None:
        assert servers_for_task("escribe un poema sobre gatos") == ()

    def test_all_returned_names_exist_in_catalog(self) -> None:
        known = set(catalog_servers())
        for keywords in TASK_SERVER_KEYWORDS:
            for name in keywords[1]:
                assert name in known, f"server inexistente en SSOT: {name}"

    def test_selection_is_deduped_and_ordered(self) -> None:
        tools = servers_for_task("decompila el binario y hazle reverse a la url")
        assert len(tools) == len(set(tools))
