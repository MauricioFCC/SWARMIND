"""Agent Discovery parsing — frontmatter YAML e inferencia de perfiles.

Extraccion mecanica del modulo original
``harness/orchestrator/agent_discovery.py`` (sin cambios de logica
ni firmas): resolucion de ruta, parseo de frontmatter y inferencia
de campos desde filename y contenido.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any

from .keywords import _CAPABILITY_KEYWORDS, _DOMAIN_KEYWORDS

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _get_agents_dir() -> Path:
    """Resuelve la ruta a .opencode/agents/ desde la ubicacion de este archivo."""
    # Este archivo esta en harness/orchestrator/agent_discovery/
    base = Path(__file__).resolve().parent.parent.parent.parent
    agents_dir = base / ".opencode" / "agents"
    if agents_dir.exists():
        return agents_dir
    # Fallback: buscar desde cwd
    cwd_agents = Path.cwd() / ".opencode" / "agents"
    if cwd_agents.exists():
        return cwd_agents
    return agents_dir


# ---------------------------------------------------------------------------
# Frontmatter parsing (YAML)
# ---------------------------------------------------------------------------

def _try_import_yaml():
    """Lazy import of yaml; returns module or None."""
    try:
        import yaml  # type: ignore
        return yaml
    except ImportError:
        return None


@functools.lru_cache(maxsize=128)
def _parse_frontmatter(content: str, filename: str) -> dict[str, Any] | None:
    """
    Parsea frontmatter YAML entre marcadores ---.

    Si no hay frontmatter o falla el parseo, retorna None.

    Cacheado por (content, filename) — cada archivo se parsea una sola vez.
    """
    content_stripped = content.lstrip()
    if not content_stripped.startswith("---"):
        return None

    # Encontrar el --- de cierre
    end_idx = content_stripped.find("---", 3)
    if end_idx == -1:
        return None

    yaml_str = content_stripped[3:end_idx]
    yaml_module = _try_import_yaml()
    if yaml_module is None:
        return None

    try:
        fm = yaml_module.safe_load(yaml_str)
    except Exception:  # noqa: BLE001
        return None

    if not isinstance(fm, dict):
        return None

    return {
        "name": str(fm.get("name", filename)),
        "domain": str(fm.get("domain", "universal")),
        "triggers": list(fm.get("triggers", []) or []),
        "capabilities": list(fm.get("capabilities", []) or []),
        "aliases": list(fm.get("aliases", []) or []),
        "description": str(fm.get("description", "")),
        "role": str(fm.get("role", "")),
    }


# ---------------------------------------------------------------------------
# Inference from file content (when no frontmatter)
# ---------------------------------------------------------------------------

def _infer_from_content(filename_stem: str, content: str) -> dict[str, Any]:
    """
    Infiere nombre, dominio, triggers y capacidades desde el filename y contenido.

    Args:
        filename_stem: Nombre del archivo sin extension (e.g., "software-engineer")
        content: Contenido completo del archivo .md

    Returns:
        Dict con campos name, domain, triggers, capabilities, aliases, description
    """
    name = filename_stem
    content_lower = content.lower()

    # Inferir dominio por keywords en contenido
    domain = "universal"
    max_matches = 0
    for keywords, dom in _DOMAIN_KEYWORDS:
        matches = sum(1 for kw in keywords if kw in content_lower)
        if matches > max_matches:
            max_matches = matches
            domain = dom

    # Inferir triggers: primeras lineas de contenido relevantes
    triggers: list[str] = []
    trigger_patterns = [
        r"@(\w[\w-]*)",           # @rol mentions
        r"!(\w[\w-]*)",           # !comandos
        r"(?:cuando|when|trigger)\s*(?:\:|on)\s*(.+?)[\n\.]",
    ]
    for pattern in trigger_patterns:
        for match in re.finditer(pattern, content):
            triggers.append(match.group(1).strip())

    # Inferir capacidades desde keywords
    capabilities: list[str] = []
    seen_caps: set = set()
    for pattern, cap in _CAPABILITY_KEYWORDS:
        if re.search(pattern, content_lower) and cap not in seen_caps:
            capabilities.append(cap)
            seen_caps.add(cap)

    # Inferir alias: primera palabra del filename sin guiones
    alias_map = {
        "project-manager": "pm",
        "software-engineer": "swe",
        "security-engineer": "sec",
        "data-architect": "data",
        "devops-sre": "devops",
        "frontend-engineer": "frontend",
        "mobile-engineer": "mobile",
        "ai-engineer": "ai",
        "quality-gate": "qa",
        "documentation-specialist": "docs",
        "requirements-analyst": "ra",
        "enterprise-architect": "architect",
        "quant-developer": "quant",
        "quant-scientist": "scientist",
        "risk-manager": "risk",
        "trading-operations": "ops",
        "context-engineer": "context",
        "tool-mcp-engineer": "mcp",
        "evolve-researcher": "evolve",
        "evolve-engineer": "evolve",
        "evolve-analyzer": "evolve",
    }
    aliases = [alias_map.get(name, name.split("-")[0])]

    # Inferir descripcion: primera linea despues del titulo
    description = ""
    for line in content.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---") and not line.startswith("!"):
            description = line[:120]
            break

    return {
        "name": name,
        "domain": domain,
        "triggers": triggers[:10],  # limitar a 10
        "capabilities": capabilities[:10],
        "aliases": aliases,
        "description": description,
    }


# ---------------------------------------------------------------------------
# Agent profile parsing
# ---------------------------------------------------------------------------

def parse_agent_profile(md_file: Path) -> dict[str, Any] | None:
    """
    Parsea un archivo .md de agente y extrae su perfil.

    Primero intenta leer el perfil pre-compilado (.agent.min.md) si existe,
    que ahorra ~40-60% de tokens. Si no, lee el archivo .md completo.
    Luego parsea frontmatter YAML; si no existe, infiere desde filename y contenido.

    Args:
        md_file: Ruta al archivo .md del agente

    Returns:
        Dict con name, domain, triggers, capabilities, aliases, description
        o None si el archivo no es un perfil valido.
    """
    if not md_file.exists() or md_file.suffix.lower() != ".md":
        return None

    # Prefer pre-compiled agent prompt (.agent.min.md) si existe
    compiled_path = md_file.with_suffix('.agent.min.md')
    if compiled_path.exists():
        source_path = compiled_path
    else:
        source_path = md_file

    try:
        content = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    filename_stem = md_file.stem

    # 1. Intentar parsear frontmatter YAML
    agent = _parse_frontmatter(content, filename_stem)

    # 2. Inferir desde filename y contenido (campos faltantes)
    inferred = _infer_from_content(filename_stem, content)

    if agent:
        # Merge: frontmatter tiene prioridad, pero inferimos campos faltantes
        for key in ("triggers", "capabilities", "aliases", "domain"):
            if not agent.get(key) and inferred.get(key):
                agent[key] = inferred[key]
        # Si falta description, usar la inferida
        if not agent.get("description") and inferred.get("description"):
            agent["description"] = inferred["description"]
        return agent

    # 3. Fallback total: solo datos inferidos
    return inferred
