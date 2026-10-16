"""mcp_opencode.py — traduce la SSOT MCP del harness a la config de opencode.

WHAT: convierte los servers de ``harness/tools_sandbox/mcp_servers.yaml`` a la
forma ``mcp.servers`` que consume OpenCode V2 (``type: local|remote``),

WHY: la SSOT MCP vive en el harness (``MCPManager``); opencode necesita su
propia config ``mcp`` para poder USAR esos servers. Sin esta traduccion, las
herramientas anexadas quedan invisibles para opencode. Lo invoca el acople
oficial ``scripts/deploy_all.py --sync-global`` (via ``sync_opencode_global``).

Mapeo (OpenCode V2):
    - ``transport: stdio`` -> ``{type: local, command: [cmd, *args]}``
    - ``transport: http``  -> ``{type: remote, url}``
    - ``env`` con ``${VAR}`` -> ``{env:VAR}`` (sustitucion de OpenCode)
    - ``disabled: true`` salvo que el server este en :data:`DEFAULT_ACTIVE`
      (set curado de servers autocontenidos: sin credenciales ni engines).

No destructivo: preserva servers ya presentes en la config que no esten en la
SSOT (p. ej. los que anada el operador a mano).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

logger = logging.getLogger("harness.tools_sandbox.mcp_opencode")

#: Patron de interpolacion de entorno en el YAML de la SSOT (``${VAR}``).
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)\}")

#: Servers que opencode conecta por defecto: autocontenidos y LIGEROS (uvx/npx
#: puros, sin credenciales, engines ni navegador). El resto se registra
#: `disabled` y se habilita desde opencode cuando haga falta (evita timeouts de
#: arranque por descargas npx o engines ausentes).
DEFAULT_ACTIVE: frozenset[str] = frozenset(
    {
        "fetch",
        "time",
        "sequentialthinking",
    }
)

#: Timeout minimo de arranque MCP (ms) que se garantiza en
#: ``mcp.timeout.{catalog,execution}`` (canonical V2; V1 usaba
#: ``experimental.mcp_timeout`` y se migra en :func:`merge_into_config`).
#: El default de OpenCode (30s) no alcanza para un server stdio servido por
#: ``npx`` en frio (descarga del paquete): OpenCode lo reporta
#: ``failed: Request timed out`` (caso verificado de ``sequentialthinking``).
#: 90s cubre la instalacion en frio sin degradar el arranque de los servers
#: ya cacheados.
MCP_TIMEOUT_MS: int = 90_000


def env_references(env: Mapping[str, Any] | None) -> dict[str, str]:
    """Convierte ``env`` del YAML a referencias de entorno de opencode.

    Args:
        env: Mapa de variables del server (``KEY: "${VAR}"`` o valor literal).

    Returns:
        Mapa con ``${VAR}`` -> ``{env:VAR}`` (OpenCode) y literales intactos.
    """
    out: dict[str, str] = {}
    for key, value in (env or {}).items():
        text = str(value)
        match = _ENV_PATTERN.fullmatch(text)
        out[str(key)] = f"{{env:{match.group(1)}}}" if match else text
    return out


def build_server_entry(server: Mapping[str, Any]) -> dict[str, Any]:
    """Traduce un server de la SSOT a una entrada ``mcp.servers`` de OpenCode.

    Args:
        server: Entrada del YAML (``name``/``transport``/``command``/``args``/
            ``env``/``url``).

    Returns:
        Entrada ``{type: local|remote, ...}`` con ``disabled`` segun
        :data:`DEFAULT_ACTIVE`.
    """
    name = str(server["name"])
    transport = str(server.get("transport", "stdio"))
    entry: dict[str, Any] = {}
    if transport == "stdio":
        entry["type"] = "local"
        entry["command"] = [
            str(server.get("command", "")),
            *[str(arg) for arg in server.get("args", []) or []],
        ]
        env = env_references(server.get("env"))
        if env:
            entry["environment"] = env
    else:
        entry["type"] = "remote"
        entry["url"] = str(server.get("url", ""))
        env = env_references(server.get("env"))
        if env:
            entry["headers"] = env
    if name not in DEFAULT_ACTIVE:
        entry["disabled"] = True
    return entry


def build_mcp_servers(servers: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Construye el mapa ``mcp.servers`` completo desde la lista de la SSOT.

    Args:
        servers: Lista de servers del YAML.

    Returns:
        Mapa ``nombre -> entrada`` listo para ``config["mcp"]["servers"]``.
    """
    return {str(s["name"]): build_server_entry(s) for s in servers}


def merge_into_config(
    config: Mapping[str, Any], servers: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """Inyecta ``mcp.servers`` en una config de OpenCode preservando el resto.

    Preserva servers ya presentes que NO esten en la SSOT (no destructivo: el
    operador puede tener servers propios). Ademas garantiza
    ``mcp.timeout.{catalog,execution} >=`` :data:`MCP_TIMEOUT_MS` (forma
    nativa V2) y migra/limpia el campo V1 ``experimental.mcp_timeout``.

    WHY: OpenCode arranca los servers stdio con un timeout propio (30s por
    defecto). Un server servido por ``npx`` en frio tarda mas (descarga del
    paquete) y OpenCode lo reporta ``failed: Request timed out`` — caso real de
    ``sequentialthinking``. Subir el timeout es portable y no toca la SSOT.

    Args:
        config: Config actual (dict) de ``opencode.json``/``.jsonc``.
        servers: Lista de servers de la SSOT.

    Returns:
        Nueva config con ``mcp.servers`` (no muta la original).
    """
    merged: dict[str, Any] = dict(config)
    existing = merged.get("mcp")
    existing_servers = (
        dict(existing.get("servers", {})) if isinstance(existing, dict) else {}
    )
    existing_servers.update(build_mcp_servers(servers))
    existing_timeout = (
        dict(existing.get("timeout", {})) if isinstance(existing, dict) else {}
    )

    # Timeout V1 legado (experimental.mcp_timeout) -> canonical V2 mcp.timeout.
    experimental = dict(merged.get("experimental") or {})
    legacy_raw = experimental.pop("mcp_timeout", 0)
    try:
        legacy_timeout = int(legacy_raw or 0)
    except (TypeError, ValueError):
        legacy_timeout = 0
    if experimental:
        merged["experimental"] = experimental
    else:
        merged.pop("experimental", None)

    timeout: dict[str, int] = {}
    for key in ("catalog", "execution"):
        try:
            current = int(existing_timeout.get(key, 0) or 0)
        except (TypeError, ValueError):
            current = 0
        timeout[key] = max(current, legacy_timeout, MCP_TIMEOUT_MS)
    merged["mcp"] = {"servers": existing_servers, "timeout": timeout}
    return merged


def load_servers(path: Path) -> list[dict[str, Any]]:
    """Carga la lista de servers de la SSOT MCP (YAML).

    Args:
        path: Ruta del YAML de servers.

    Returns:
        Lista de dicts con ``name``; vacia si el archivo falta o no tiene servers.
    """
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning(
            "mcp_opencode: %s ilegible (%s). WHERE: load_servers", path, exc
        )
        return []
    servers = data.get("servers", []) if isinstance(data, dict) else []
    return [s for s in servers if isinstance(s, dict) and s.get("name")]


def sync_config_file(
    path: Path, servers: Iterable[Mapping[str, Any]], dry_run: bool = False
) -> bool:
    """Escribe ``mcp.servers`` en una config de opencode (idempotente).

    Args:
        path: Ruta del ``opencode.json``/``.jsonc`` a parchear.
        servers: Lista de servers de la SSOT.
        dry_run: Si True, no escribe.

    Returns:
        True si el archivo quedo (o quedaria) en sync; False si no se pudo leer
        un JSON valido (se conserva sin tocar).
    """
    if path.is_file():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "mcp_opencode: %s ilegible (%s); conservo sin tocar. "
                "WHERE: sync_config_file", path, exc,
            )
            return False
    else:
        current = {}
    desired = merge_into_config(current, servers)
    if current == desired:
        return True
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(desired, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return True
