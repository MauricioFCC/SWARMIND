"""Scanner de configuracion MCP (ciclo 11.18 — OWASP MCP Top-10).

WHAT: auditoria determinista de la config MCP de OpenCode (JSONC real:
comentarios + trailing commas) contra las categorias OWASP MCP Top-10:
RUG PULL / lack of version pins (payload flotando en ``latest``), comandos
shell crudos (ejecucion arbitraria sin pin posible), secretos en ``env``
(masking SEG: nunca se imprime el valor), transporte sin TLS y endpoints
internos (superficie LLM-SSRF).

WHY: 17 servidores MCP configurados a mano sin verificacion automatizada =
superficie supply-chain/SSRF invisible en cada sesion del harness.

WHERE: ``harness/security/mcp_security_scan.py``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

#: Comandos que ejecutan payload arbitrario sin pin posible (alto riesgo).
SHELL_COMMANDS = frozenset({"sh", "bash", "zsh", "cmd", "powershell", "pwsh", "sudo"})
#: Gestores de paquetes cuyo payload flota si no esta versionado.
PINNED_COMMANDS = frozenset({"npx", "uvx", "uv", "pip", "pipx", "npm", "yarn", "pnpm"})
#: Nombres de variables de entorno que delatan secretos (masking obligatorio).
SECRET_NAME_RE = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|CREDENTIAL)", re.IGNORECASE)
#: Pin estilo ``pkg@1.2.3`` / ``pkg@2026.10.10`` (npx, uvx).
PIN_AT_RE = re.compile(r"@\d+\.\d+")
#: Pin estilo ``pkg==1.2.3`` (pip).
PIN_EQ_RE = re.compile(r"==\d+(\.\d+)*")
#: Hosts de loopback/red privada (superficie SSRF).
_PRIVATE_PREFIXES = ("10.", "192.168.", "169.254.")
_PRIVATE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True)
class McpFinding:
    """Hallazgo inmutable de una auditoria MCP (orden determinista)."""

    server: str
    category: str
    severity: str
    detail: str


def parse_opencode_jsonc(text: str) -> dict[str, object]:
    """Parsea JSONC de OpenCode (comentarios ``//``/``/* */`,`, final).

    Los comentarios se blanked (no eliminados) para preservar la
    numeracion de lineas en errores accionables.

    Raises:
        ValueError: Si el texto no es JSONC valido (con ``linea N``) o el
            resultado no es un objeto JSON.
    """
    no_block = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.DOTALL)
    lines: list[str] = []
    for raw in no_block.splitlines():
        index = _comment_index(raw)
        lines.append(raw if index < 0 else raw[:index])
    cleaned = re.sub(r",(\s*[}\]])", r"\1", "\n".join(lines))
    try:
        config = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"WHAT: linea {exc.lineno} del opencode.jsonc no es JSON valido "
            f"({exc.msg}). WHY: el scanner exige config parseable. "
            "WHERE: parse_opencode_jsonc."
        ) from None
    if not isinstance(config, dict):
        raise ValueError(  # noqa: TRY004 - ValueError es el contrato del parser
            "WHAT: la raiz del opencode.jsonc no es un objeto. WHY: se "
            "espera {{'mcp': ...}}. WHERE: parse_opencode_jsonc."
        )
    return config


def scan_mcp_config(config: Mapping[str, object]) -> tuple[McpFinding, ...]:
    """Audita servidores MCP contra el OWASP MCP Top-10 (ordenado).

    Args:
        config: Config parseada con la seccion ``mcp`` obligatoria.

    Returns:
        Tupla de ``McpFinding`` ordenada por (servidor, categoria).

    Raises:
        ValueError: Sin seccion ``mcp`` o con servidores malformados.
    """
    mcp = config.get("mcp")
    if not isinstance(mcp, Mapping):
        raise ValueError(  # noqa: TRY004 - ValueError es el contrato del scanner
            "WHAT: config sin seccion 'mcp'. WHY: el scanner audita "
            "servidores MCP. WHERE: scan_mcp_config."
        )
    servers = mcp.get("servers")
    if not isinstance(servers, Mapping):
        servers = mcp
    findings: list[McpFinding] = []
    for server in sorted(servers):
        entry = servers[server]
        if not isinstance(entry, Mapping):
            raise ValueError(  # noqa: TRY004 - ValueError es el contrato del scanner
                f"WHAT: servidor '{server}' con forma invalida. WHY: se "
                "espera un objeto. WHERE: scan_mcp_config."
            )
        findings.extend(_scan_server(str(server), entry))
    return tuple(sorted(findings, key=lambda f: (f.server, f.category)))


def _comment_index(line: str) -> int:
    """Indice del ``//`` de comentario (ignora el de ``://`` en URLs)."""
    index = line.find("//")
    while index >= 0:
        if index == 0 or line[index - 1] != ":":
            return index
        index = line.find("//", index + 2)
    return -1


def _scan_server(name: str, entry: Mapping[str, object]) -> list[McpFinding]:
    """Reglas por servidor: shell, pin, secretos, transporte y SSRF."""
    findings: list[McpFinding] = []
    argv = _normalize_argv(name, entry)
    if argv is not None:
        findings.extend(_scan_command(name, argv))
    url = entry.get("url")
    if url is not None:
        findings.extend(_scan_url(name, url))
    if argv is None and url is None:
        raise ValueError(
            f"WHAT: servidor '{name}' sin command ni url. WHY: no hay que "
            "auditar. WHERE: scan_mcp_config."
        )
    findings.extend(_scan_env(name, entry.get("environment", entry.get("env"))))
    return findings


def _normalize_argv(name: str, entry: Mapping[str, object]) -> list[str] | None:
    """Normaliza command (string + args, o lista argv estilo OpenCode V2)."""
    command = entry.get("command")
    if command is None:
        return None
    args = entry.get("args", [])
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ValueError(
            f"WHAT: servidor '{name}' con args no-lista-de-strings. WHY: "
            "forma invalida. WHERE: scan_mcp_config."
        )
    if isinstance(command, str):
        if not command:
            raise ValueError(
                f"WHAT: servidor '{name}' con command vacio. WHY: forma "
                "invalida. WHERE: scan_mcp_config."
            )
        return [command, *args]
    if isinstance(command, list) and all(isinstance(part, str) for part in command):
        if not command or not command[0]:
            raise ValueError(
                f"WHAT: servidor '{name}' con command argv vacio. WHY: "
                "forma invalida. WHERE: scan_mcp_config."
            )
        if args:
            raise ValueError(
                f"WHAT: servidor '{name}' con command lista + args. WHY: "
                "el argv va en una sola forma. WHERE: scan_mcp_config."
            )
        return list(command)
    raise ValueError(
        f"WHAT: servidor '{name}' con command no-string/no-argv. WHY: "
        "forma invalida. WHERE: scan_mcp_config."
    )


def _scan_command(name: str, argv: list[str]) -> list[McpFinding]:
    """Reglas de comando: shell crudo + pin de payload versionado."""
    base = argv[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1].removesuffix(".exe").lower()
    findings: list[McpFinding] = []
    if base in SHELL_COMMANDS:
        findings.append(
            McpFinding(
                server=name,
                category="shell_command",
                severity="high",
                detail=f"comando shell crudo '{base}': payload arbitrario sin pin posible",
            )
        )
    if base in PINNED_COMMANDS:
        joined = " ".join(argv)
        if not (PIN_AT_RE.search(joined) or PIN_EQ_RE.search(joined)):
            findings.append(
                McpFinding(
                    server=name,
                    category="unpinned_command",
                    severity="high",
                    detail=f"payload de '{base}' sin version fijada (rug-pull/supply-chain)",
                )
            )
    return findings


def _scan_url(name: str, url: object) -> list[McpFinding]:
    """Reglas de transporte remoto: TLS y superficie SSRF interna."""
    if not isinstance(url, str) or not url:
        raise ValueError(
            f"WHAT: servidor '{name}' con url no-string/vacia. WHY: forma "
            "invalida. WHERE: scan_mcp_config."
        )
    findings: list[McpFinding] = []
    if url.startswith("http://"):
        findings.append(
            McpFinding(
                server=name,
                category="insecure_transport",
                severity="medium",
                detail="endpoint MCP sin TLS (trafico/tool-calls en claro)",
            )
        )
    host = (urlsplit(url).hostname or "").lower()
    if host in _PRIVATE_HOSTS or host.startswith(_PRIVATE_PREFIXES):
        findings.append(
            McpFinding(
                server=name,
                category="internal_endpoint",
                severity="low",
                detail=f"host interno '{host}': superficie LLM-SSRF",
            )
        )
    return findings


def _scan_env(name: str, env: object) -> list[McpFinding]:
    """Regla de secretos en env: reporta la CLAVE con el valor enmascarado."""
    if env is None:
        return []
    if not isinstance(env, Mapping):
        raise ValueError(  # noqa: TRY004 - ValueError es el contrato del scanner
            f"WHAT: servidor '{name}' con env no-objeto. WHY: forma "
            "invalida. WHERE: scan_mcp_config."
        )
    findings: list[McpFinding] = []
    for key in sorted(env):
        if SECRET_NAME_RE.search(str(key)):
            value = env[key]
            findings.append(
                McpFinding(
                    server=name,
                    category="secret_in_env",
                    severity="high",
                    detail=f"env.{key}=<enmascarado,len={len(str(value))}>",
                )
            )
    return findings
