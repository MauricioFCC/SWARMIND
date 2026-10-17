"""Tests de la traduccion SSOT MCP -> config de opencode (mcp_opencode).

Verifican el mapeo local/remote, la sustitucion de entorno, la politica
`disabled` (DEFAULT_ACTIVE) y el merge no destructivo. Cada aserto es mordible.
"""

from __future__ import annotations

import json
from pathlib import Path

from harness.tools_sandbox.mcp_opencode import (
    DEFAULT_ACTIVE,
    MCP_TIMEOUT_MS,
    build_mcp_servers,
    build_server_entry,
    env_references,
    load_servers,
    merge_into_config,
    sync_config_file,
)

_REAL_YAML = (
    Path(__file__).resolve().parents[1] / "tools_sandbox" / "mcp_servers.yaml"
)


class TestBuildEntry:
    """Traduccion de cada server a la forma mcp.servers de OpenCode."""

    def test_stdio_becomes_local_with_command_list(self) -> None:
        entry = build_server_entry(
            {"name": "fetch", "transport": "stdio", "command": "uvx",
             "args": ["mcp-server-fetch"]}
        )
        assert entry["type"] == "local"
        assert entry["command"] == ["uvx", "mcp-server-fetch"]

    def test_http_becomes_remote_with_url(self) -> None:
        entry = build_server_entry(
            {"name": "supabase", "transport": "http",
             "url": "https://mcp.supabase.com/mcp"}
        )
        assert entry["type"] == "remote"
        assert entry["url"] == "https://mcp.supabase.com/mcp"

    def test_default_active_is_not_disabled(self) -> None:
        for name in DEFAULT_ACTIVE:
            entry = build_server_entry(
                {"name": name, "transport": "stdio", "command": "npx", "args": ["x"]}
            )
            assert "disabled" not in entry, name

    def test_non_active_is_disabled(self) -> None:
        entry = build_server_entry(
            {"name": "ghidra_mcp", "transport": "stdio", "command": "uv", "args": ["x"]}
        )
        assert entry["disabled"] is True

    def test_env_dollar_brace_becomes_opencode_substitution(self) -> None:
        entry = build_server_entry(
            {"name": "sentry", "transport": "stdio", "command": "npx", "args": ["x"],
             "env": {"SENTRY_ACCESS_TOKEN": "${SENTRY_ACCESS_TOKEN}", "LITERAL": "abc"}}
        )
        assert entry["environment"]["SENTRY_ACCESS_TOKEN"] == "{env:SENTRY_ACCESS_TOKEN}"
        assert entry["environment"]["LITERAL"] == "abc"

    def test_env_references_literal_untouched(self) -> None:
        assert env_references({"A": "plain"}) == {"A": "plain"}
        assert env_references(None) == {}


class TestMerge:
    """Merge no destructivo de mcp.servers."""

    def test_merge_preserves_foreign_servers(self) -> None:
        current = {"mcp": {"servers": {"mine": {"type": "local", "command": ["x"]}}}}
        merged = merge_into_config(
            current, [{"name": "fetch", "transport": "stdio", "command": "uvx",
                       "args": ["mcp-server-fetch"]}]
        )
        assert "mine" in merged["mcp"]["servers"]
        assert "fetch" in merged["mcp"]["servers"]

    def test_merge_preserves_unrelated_keys(self) -> None:
        merged = merge_into_config({"model": "x/y"}, [])
        assert merged["model"] == "x/y"


class TestMcpTimeout:
    """``mcp.timeout`` (nativo V2) minimo para servers stdio servidos por npx.

    Caso real: ``sequentialthinking`` (npx en frio) moria con
    ``failed: Request timed out`` al timeout por defecto de OpenCode (30s).
    ``experimental.mcp_timeout`` es V1: se normaliza pero el canonical es
    ``mcp.timeout.{catalog,execution}``.
    """

    def test_merge_fija_el_timeout_minimo(self) -> None:
        merged = merge_into_config({}, [])
        timeout = merged["mcp"]["timeout"]
        assert timeout["catalog"] == MCP_TIMEOUT_MS
        assert timeout["execution"] == MCP_TIMEOUT_MS

    def test_merge_no_baja_un_timeout_mayor(self) -> None:
        merged = merge_into_config(
            {"mcp": {"timeout": {"catalog": 120_000, "execution": 120_000}}}, []
        )
        assert merged["mcp"]["timeout"] == {"catalog": 120_000, "execution": 120_000}

    def test_merge_migra_el_timeout_v1_de_experimental(self) -> None:
        """Un config legado con ``experimental.mcp_timeout`` migra y lo limpia."""
        merged = merge_into_config({"experimental": {"mcp_timeout": 120_000}}, [])
        assert merged["mcp"]["timeout"]["catalog"] == 120_000
        assert "mcp_timeout" not in (merged.get("experimental") or {})

    def test_merge_preserva_otras_claves_experimental(self) -> None:
        merged = merge_into_config({"experimental": {"otra": True}}, [])
        assert merged["experimental"]["otra"] is True

    def test_timeout_invalido_no_explota(self) -> None:
        merged = merge_into_config({"experimental": {"mcp_timeout": "no-numero"}}, [])
        assert merged["mcp"]["timeout"]["catalog"] == MCP_TIMEOUT_MS


class TestRealSsot:
    """La SSOT real carga y produce un mapa valido (no decorativo)."""

    def test_load_real_yaml_has_servers(self) -> None:
        servers = load_servers(_REAL_YAML)
        assert len(servers) >= 20
        names = {s["name"] for s in servers}
        assert "rea" in names and "fetch" in names and "chrome_devtools" in names

    def test_build_all_servers_ids_match(self) -> None:
        servers = load_servers(_REAL_YAML)
        built = build_mcp_servers(servers)
        assert set(built) == {str(s["name"]) for s in servers}
        for entry in built.values():
            assert entry["type"] in {"local", "remote"}


class TestSyncConfigFile:
    """Escritura idempotente y preservadora."""

    def test_sync_writes_and_is_idempotent(self, tmp_path: Path) -> None:
        cfg = tmp_path / "opencode.json"
        servers = [{"name": "fetch", "transport": "stdio", "command": "uvx",
                    "args": ["mcp-server-fetch"]}]
        assert sync_config_file(cfg, servers) is True
        first = json.loads(cfg.read_text(encoding="utf-8"))
        assert "fetch" in first["mcp"]["servers"]
        # Segunda pasada: no cambia (idempotente).
        assert sync_config_file(cfg, servers) is True
        assert json.loads(cfg.read_text(encoding="utf-8")) == first

    def test_sync_preserves_existing_keys(self, tmp_path: Path) -> None:
        cfg = tmp_path / "opencode.json"
        cfg.write_text(json.dumps({"model": "a/b", "provider": {"x": 1}}), encoding="utf-8")
        sync_config_file(cfg, [{"name": "time", "transport": "stdio",
                                "command": "uvx", "args": ["mcp-server-time"]}])
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert data["model"] == "a/b"
        assert data["provider"] == {"x": 1}
        assert "time" in data["mcp"]["servers"]

    def test_sync_does_not_write_in_dry_run(self, tmp_path: Path) -> None:
        cfg = tmp_path / "opencode.json"
        sync_config_file(cfg, [{"name": "time", "transport": "stdio",
                                "command": "uvx", "args": ["mcp-server-time"]}],
                         dry_run=True)
        assert not cfg.exists()
