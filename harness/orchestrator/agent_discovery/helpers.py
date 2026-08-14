"""Agent Discovery helpers — alias, capacidades, dominios e intents.

Extraccion mecanica del modulo original
``harness/orchestrator/agent_discovery.py`` (sin cambios de logica
ni firmas): build_alias_map, resolve_agent_name, get_all_capabilities,
get_agent_for_domain, list_agents y build_intent_map.
"""
from __future__ import annotations

from typing import Any

from .discovery import discover_agents_recursive

# ---------------------------------------------------------------------------
# Alias resolution
# ---------------------------------------------------------------------------

def build_alias_map(agents: dict[str, dict[str, Any]]) -> dict[str, str]:
    """
    Construye un mapa de alias -> nombre canonico desde los agentes descubiertos.

    Incluye alias explicitos del frontmatter y alias inferidos por convencion.

    Args:
        agents: Dict de agentes descubiertos

    Returns:
        Dict[str, str] con alias -> nombre canonico del agente
    """
    alias_map: dict[str, str] = {}

    for name, info in agents.items():
        # Alias explicitos del frontmatter
        for alias in info.get("aliases", []):
            alias_map[alias.lower()] = name

        # Alias por convencion: parte antes del primer guion
        # (e.g., "software-engineer" -> "software")
        # pero solo si no hay conflicto
        primary = name.split("-")[0]
        if primary != name and primary not in alias_map:
            alias_map[primary] = name

    # Aliases hardcodeados para compatibilidad con @roles antiguos.
    # Ahora apuntan a los 5 roles universales (los viejos agentes se eliminaron).
    hardcoded_aliases = {
        # Coordinator
        "pm": "coordinator",
        "coordinator": "coordinator",
        "orchestrator": "coordinator",
        "project-manager": "coordinator",
        "context-engineer": "coordinator",
        "requirements-analyst": "coordinator",
        "tool-mcp-engineer": "coordinator",
        # Builder
        "swe": "builder",
        "builder": "builder",
        "dev": "builder",
        "software-engineer": "builder",
        "frontend-engineer": "builder",
        "frontend": "builder",
        "mobile-engineer": "builder",
        "mobile": "builder",
        "data-architect": "builder",
        "data": "builder",
        "devops-sre": "builder",
        "devops": "builder",
        "quant-developer": "builder",
        "quant": "builder",
        "ai-engineer": "builder",
        "ai": "builder",
        "enterprise-architect": "builder",
        "architect": "builder",
        # Scientist
        "scientist": "scientist",
        "quant-scientist": "scientist",
        # Guardian
        "qa": "guardian",
        "guardian": "guardian",
        "sec": "guardian",
        "security-engineer": "guardian",
        "risk-manager": "guardian",
        "risk": "guardian",
        "docs": "guardian",
        "documentation-specialist": "guardian",
        "trading-operations": "guardian",
        "ops": "guardian",
        "quality-gate": "guardian",
        # Evolve
        "evolve": "evolve",
        "evolve-researcher": "evolve",
        "evolve-engineer": "evolve",
        "evolve-analyzer": "evolve",
    }
    for alias, name in hardcoded_aliases.items():
        alias_map[alias] = name  # Hardcoded aliases override inferred ones

    return alias_map


def resolve_agent_name(alias_or_name: str, agents: dict[str, Any] | None = None) -> str:
    """
    Resuelve un alias o nombre a su nombre canonico de agente.

    Args:
        alias_or_name: Alias (@pm, @swe) o nombre ("project-manager")
        agents: Dict de agentes descubiertos (opcional, auto-descubre si es None)

    Returns:
        Nombre canonico del agente, o string vacio si no se encuentra.
    """
    if agents is None:
        agents = discover_agents_recursive()

    key = alias_or_name.lower().replace("-", "_")

    # Busqueda directa
    if alias_or_name in agents:
        return alias_or_name

    # Construir alias map
    alias_map = build_alias_map(agents)

    return alias_map.get(key, "")


# ---------------------------------------------------------------------------
# Capability & Domain helpers
# ---------------------------------------------------------------------------

def get_all_capabilities(agents: dict[str, Any] | None = None) -> dict[str, list[str]]:
    """
    Retorna un dict con nombre de agente -> lista de capacidades.

    Args:
        agents: Dict de agentes (auto-descubre si es None)

    Returns:
        Dict[str, List[str]] con capacidades por agente
    """
    if agents is None:
        agents = discover_agents_recursive()

    return {
        name: info.get("capabilities", [])
        for name, info in agents.items()
    }


def get_agent_for_domain(domain: str, agents: dict[str, Any] | None = None) -> str:
    """
    Retorna el agente primario para un dominio dado.

    Args:
        domain: Nombre del dominio
        agents: Dict de agentes (auto-descubre si es None)

    Returns:
        Nombre del agente, o "project-manager" como fallback
    """
    if agents is None:
        agents = discover_agents_recursive()

    for name, info in agents.items():
        if info.get("domain") == domain:
            return name

    return "project-manager"


def list_agents(agents: dict[str, Any] | None = None) -> list[str]:
    """
    Retorna lista ordenada de nombres de agentes.

    Args:
        agents: Dict de agentes (auto-descubre si es None)

    Returns:
        Lista ordenada de nombres
    """
    if agents is None:
        agents = discover_agents_recursive()
    return sorted(agents.keys())


def build_intent_map(agents: dict[str, Any] | None = None) -> dict[str, str]:
    """
    Construye un mapa de keyword -> agente desde los triggers de cada agente.

    Cada trigger en el frontmatter del agente se convierte en una entrada
    en el mapa de intents.

    Args:
        agents: Dict de agentes (auto-descubre si es None)

    Returns:
        Dict[str, str] con keyword -> nombre de agente
    """
    if agents is None:
        agents = discover_agents_recursive()

    intent_map: dict[str, str] = {}
    for name, info in agents.items():
        for trigger in info.get("triggers", []):
            trigger_lower = trigger.lower().strip()
            if trigger_lower:
                intent_map[trigger_lower] = name

    return intent_map
