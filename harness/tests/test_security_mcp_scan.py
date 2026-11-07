"""Contrato del scanner de configuracion MCP (ciclo 11.18 — OWASP MCP Top-10).

WHAT: verifica ``harness/security/mcp_security_scan.py`` contra la frontera:

- **OWASP MCP Top-10** (2025): RUG PULL (payload que flota en ``latest``),
  LACK OF TOOLS VERSION PINS, LLM SSRF (endpoints internos/TLS), secretos
  expuestos en ``env`` de servidores.
- La config real de OpenCode (``~/.config/opencode/opencode.jsonc``) es
  JSONC (comentarios + trailing commas) — el scanner debe parsearla sin
  reventar y sin imprimir secretos (masking SEG).

WHY: 17 servidores MCP configurados a mano sin auditoria automatizada =
superficie supply-chain y SSRF invisible en cada sesion.

WHERE: ``harness/security/mcp_security_scan.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.security.mcp_security_scan import (
    McpFinding,
    parse_opencode_jsonc,
    scan_mcp_config,
)

CONFIG_OK = """
{
  // servidor local con pin
  "mcp": {
    "fetch": {
      "type": "local",
      "command": "uvx",
      "args": ["mcp-server-fetch@2026.10.10"],
      "env": {}
    }
  }
}
"""


class TestParseJsonc:
    """Parser JSONC (comentarios de linea, bloque y trailing comma)."""

    def test_comentarios_y_trailing_comma(self) -> None:
        config = parse_opencode_jsonc(CONFIG_OK)

        assert config["mcp"]["fetch"]["command"] == "uvx"

    def test_url_con_doble_barra_no_se_corta(self) -> None:
        text = '{"mcp": {"r": {"url": "https://api.example.com/mcp"}}}'
        config = parse_opencode_jsonc(text)

        assert config["mcp"]["r"]["url"] == "https://api.example.com/mcp"

    def test_json_corrupto_explicita_linea(self) -> None:
        with pytest.raises(ValueError, match=r"linea 1"):
            parse_opencode_jsonc("{esto no es json")


class TestScanMcpConfig:
    """Reglas OWASP: shell, pin, secretos en env, transporte, SSRF."""

    def test_config_sin_mcp_es_error(self) -> None:
        with pytest.raises(ValueError, match="mcp"):
            scan_mcp_config({})

    def test_comando_shell_crudo_es_alto(self) -> None:
        config = {
            "mcp": {
                "peligro": {
                    "type": "local",
                    "command": "bash",
                    "args": ["-c", "iniciar servidor"],
                }
            }
        }

        findings = scan_mcp_config(config)

        assert [f.category for f in findings] == ["shell_command"]
        assert findings[0].severity == "high"

    def test_npx_sin_pin_es_supply_chain(self) -> None:
        config = {"mcp": {"srv": {"command": "npx", "args": ["paquete-sin-version"]}}}

        findings = scan_mcp_config(config)

        assert [f.category for f in findings] == ["unpinned_command"]

    def test_npx_con_pin_no_reporta(self) -> None:
        config = {"mcp": {"srv": {"command": "npx", "args": ["paquete@1.2.3"]}}}

        assert scan_mcp_config(config) == ()

    def test_pip_con_doble_igual_es_pin(self) -> None:
        unpinned = {"mcp": {"s": {"command": "pip", "args": ["paquete"]}}}
        pinned = {"mcp": {"s": {"command": "pip", "args": ["paquete==1.0.0"]}}}

        assert [f.category for f in scan_mcp_config(unpinned)] == ["unpinned_command"]
        assert scan_mcp_config(pinned) == ()

    def test_env_con_secreto_se_enmascara(self) -> None:
        config = {
            "mcp": {
                "s": {
                    "command": "uvx",
                    "args": ["srv@1.0"],
                    "env": {"OPENAI_API_KEY": "valor-real-secreto"},
                }
            }
        }

        findings = scan_mcp_config(config)

        assert [f.category for f in findings] == ["secret_in_env"]
        assert findings[0].severity == "high"
        assert "valor-real-secreto" not in findings[0].detail, "masking SEG"

    def test_url_http_es_insegura_y_https_no(self) -> None:
        http = {"mcp": {"r": {"url": "http://remoto.example.com/mcp"}}}
        https = {"mcp": {"r": {"url": "https://remoto.example.com/mcp"}}}

        assert [f.category for f in scan_mcp_config(http)] == ["insecure_transport"]
        assert scan_mcp_config(https) == ()

    def test_url_interna_es_superficie_ssrf(self) -> None:
        config = {"mcp": {"r": {"url": "https://10.0.0.5:9000/mcp"}}}

        findings = scan_mcp_config(config)

        assert [f.category for f in findings] == ["internal_endpoint"]
        assert findings[0].severity == "low"

    def test_orden_determinista_por_servidor(self) -> None:
        config = {
            "mcp": {
                "zeta": {"command": "npx", "args": ["sin-pin"]},
                "alfa": {"command": "bash", "args": ["-c", "x"]},
            }
        }

        findings = scan_mcp_config(config)

        assert [f.server for f in findings] == ["alfa", "zeta"]

    def test_servidor_con_forma_invalida_es_error(self) -> None:
        config = {"mcp": {"s": {"type": "local"}}}

        with pytest.raises(ValueError, match="command"):
            scan_mcp_config(config)

    def test_finding_es_frozen(self) -> None:
        from dataclasses import FrozenInstanceError

        finding = McpFinding(server="s", category="c", severity="low", detail="d")

        with pytest.raises(FrozenInstanceError):
            finding.severity = "high"  # type: ignore[misc]


class TestFormaRealOpenCode:
    """Contratos de la forma real del opencode.jsonc V2 (verificada)."""

    def test_seccion_mcp_con_subclave_servers(self) -> None:
        config = {
            "mcp": {
                "timeout": 5000,
                "servers": {"s": {"command": ["npx", "-y", "sin-pin"]}},
            }
        }

        findings = scan_mcp_config(config)

        assert [(f.server, f.category) for f in findings] == [("s", "unpinned_command")]

    def test_command_en_forma_argv_lista_con_pin(self) -> None:
        config = {"mcp": {"s": {"command": ["uvx", "mcp-server-fetch@2026.10.10"]}}}

        assert scan_mcp_config(config) == ()

    def test_command_argv_shell_crudo(self) -> None:
        config = {"mcp": {"s": {"command": ["powershell", "-Command", "x"]}}}

        findings = scan_mcp_config(config)

        assert [f.category for f in findings] == ["shell_command"]

    def test_environment_key_detecta_secreto_enmascarado(self) -> None:
        config = {
            "mcp": {
                "s": {
                    "command": ["uvx", "srv@1.0"],
                    "environment": {"GITHUB_TOKEN": "ghp_valor-real"},
                }
            }
        }

        findings = scan_mcp_config(config)

        assert [f.category for f in findings] == ["secret_in_env"]
        assert "ghp_valor-real" not in findings[0].detail


class TestConfigReal:
    """El scanner corre sobre la config real del harness sin reventar."""

    def test_config_real_de_opencode_se_escanea(self) -> None:
        path = Path.home() / ".config" / "opencode" / "opencode.jsonc"
        if not path.exists():
            pytest.skip("config de OpenCode no disponible en esta maquina")

        config = parse_opencode_jsonc(path.read_text(encoding="utf-8"))
        findings = scan_mcp_config(config)

        assert isinstance(findings, tuple)
        for finding in findings:
            assert finding.server and finding.category and finding.detail
