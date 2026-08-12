"""Agent Discovery recursive — descubrimiento recursivo de agentes.

Extraccion mecanica del modulo original
``harness/orchestrator/agent_discovery.py`` (sin cambios de logica
ni firmas): discover_agents_recursive con Path.rglob() y cache.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

from .parsing import _get_agents_dir, parse_agent_profile

# ---------------------------------------------------------------------------
# Recursive agent discovery
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def discover_agents_recursive(agents_dir: str | None = None) -> dict[str, dict[str, Any]]:
    """
    Descubre agentes recursivamente desde .opencode/agents/.

    Usa Path.rglob() para encontrar recursivamente todos los archivos .md
    y extrae sus perfiles. Los resultados se cachean con lru_cache para
    evitar lecturas repetidas de disco.

    Args:
        agents_dir: Directorio donde buscar (default: .opencode/agents/)

    Returns:
        Dict[str, Dict] con nombre del agente -> perfil
        Cada perfil contiene: name, domain, triggers, capabilities, aliases, description
    """
    agents: dict[str, dict[str, Any]] = {}

    if agents_dir:
        search_path = Path(agents_dir)
    else:
        search_path = _get_agents_dir()

    if not search_path.exists():
        return agents

    # RECURSIVO: rglob encuentra todos los .md recursivamente
    # NOTA: Saltamos archivos .agent.min.md porque se cargan via el .md original
    for md_file in sorted(search_path.rglob("*.md")):
        if md_file.name.endswith(".agent.min.md"):
            continue
        agent = parse_agent_profile(md_file)
        if agent and agent.get("name"):
            agents[agent["name"]] = agent

    return agents
