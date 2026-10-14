"""mcp_catalog.py — acceso al catalogo MCP y mapeo tarea -> herramientas.

WHAT: lee la SSOT ``harness/tools_sandbox/mcp_servers.yaml`` y expone
(1) los nombres de servers y (2) una seleccion por tarea (keyword -> servers),
para que el orquestador aplique agente + skills + HERRAMIENTAS de forma cableada.

WHY: "usar la herramienta correcta para el trabajo" (filosofia REA): el
DispatchPlan ya compone agente + skills; faltaban las herramientas (MCP). Este
mapa las cablea sin reimplementar routing (IDP): reusa el catalogo verificado.

WHERE: ``harness/orchestrator/coordinator_dispatch.dispatch`` (campo ``tools``)
y `harness/tools_sandbox/mcp_opencode` (registro en opencode).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger("harness.tools_sandbox.mcp_catalog")

#: Ruta de la SSOT de servers MCP.
CATALOG_PATH = (
    Path(__file__).resolve().parent / "mcp_servers.yaml"
)

#: Keyword (substring, case-insensitive) -> servers MCP del catalogo que aplican.
#: Solo se devuelven los que EXISTAN en la SSOT (no se inventan herramientas).
TASK_SERVER_KEYWORDS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("inversa", "reverse", "decompil", "decompile", "ghidra", "asar",
         "binario", "xref", "malware", "frida", "instrumenta"),
        ("rea", "rc_devtools", "ghidra_mcp", "radare2"),
    ),
    (
        ("browser", "navegador", "playwright", "e2e", "ui web", "pantalla",
         "performance web", "devtools"),
        ("playwright", "chrome_devtools"),
    ),
    (
        ("scrape", "crawl", "scraping", "extraer web"),
        ("firecrawl", "fetch"),
    ),
    (
        ("url", "fetch", "descarga", "http", "web page"),
        ("fetch", "firecrawl"),
    ),
    (
        ("razona", "razonamiento", "paso a paso", "cadena de pensamiento",
         "thinking", "descompone el problema"),
        ("sequentialthinking",),
    ),
    (
        ("documentacion de libreria", "docs de", "context7", "version de la api"),
        ("context7",),
    ),
    (
        ("postgres", "sql", "base de datos", "database", "query sql", "supabase"),
        ("postgres", "supabase"),
    ),
    (
        ("kubernetes", "k8s", "cluster", "helm", "pods"),
        ("kubernetes",),
    ),
    (
        ("github", "pull request", "repositorio", "pr de"),
        ("github",),
    ),
    (
        ("git ", "commit", "diff", "rama git"),
        ("git",),
    ),
    (
        ("notion", "pagina de notas", "wiki"),
        ("notion",),
    ),
    (
        ("sentry", "errores en produccion", "traza de error"),
        ("sentry",),
    ),
    (
        ("hora", "zona horaria", "timezone", "fecha actual"),
        ("time",),
    ),
    (
        ("memoria persistente", "grafo de conocimiento"),
        ("memory",),
    ),
)


@lru_cache(maxsize=1)
def _catalog(path: str) -> tuple[dict, ...]:
    """Carga (cacheada) la lista de servers del catalogo.

    Args:
        path: Ruta del YAML (string para poder cachear).

    Returns:
        Tupla de dicts de servers (vacia si el archivo falta).
    """
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning(
            "mcp_catalog: %s ilegible (%s). WHERE: _catalog", path, exc
        )
        return ()
    servers = data.get("servers", []) if isinstance(data, dict) else []
    return tuple(s for s in servers if isinstance(s, dict) and s.get("name"))


def catalog_servers() -> tuple[str, ...]:
    """Nombres de todos los servers del catalogo (SSOT), en orden.

    Returns:
        Tupla de nombres.
    """
    return tuple(str(s["name"]) for s in _catalog(str(CATALOG_PATH)))


def servers_for_task(task: str) -> tuple[str, ...]:
    """Selecciona los servers MCP aplicables a una tarea por keyword.

    Solo devuelve nombres presentes en la SSOT (0 herramientas inventadas).

    Args:
        task: Descripcion de la tarea.

    Returns:
        Tupla de nombres de servers del catalogo que aplican (vacia si ninguno).
    """
    if not task or not task.strip():
        return ()
    lowered = task.strip().lower()
    known = set(catalog_servers())
    selected: list[str] = []
    for keywords, servers in TASK_SERVER_KEYWORDS:
        if any(k in lowered for k in keywords):
            for name in servers:
                if name in known and name not in selected:
                    selected.append(name)
    return tuple(selected)
