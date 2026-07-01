"""
Agent Discovery — Recursive agent profile parser.

Reemplaza los ~200+ líneas de mappings hardcodeados en delegation_engine.py,
delegate.py, run.py y AGENTS.md con un descubrimiento recursivo desde
.opencode/agents/*.md.

Patrón RECURSIVO: usa Path.rglob() para descubrir agentes recursivamente,
eliminando la necesidad de mantener registros manuales en múltiples sitios.

El YAML frontmatter de cada .md define:
  - name: nombre del agente (default: filename)
  - domain: dominio principal (default: "universal")
  - triggers: palabras clave para routing por intent
  - capabilities: capacidades técnicas
  - aliases: alias cortos (@pm, @swe, etc.)
  - description: descripción del rol

Si un .md no tiene frontmatter, se infieren los campos desde el filename y
el contenido del archivo mediante búsqueda de keywords.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import functools


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _get_agents_dir() -> Path:
    """Resuelve la ruta a .opencode/agents/ desde la ubicación de este archivo."""
    # Este archivo está en harness/orchestrator/
    base = Path(__file__).resolve().parent.parent.parent
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
def _parse_frontmatter(content: str, filename: str) -> Optional[Dict[str, Any]]:
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
    except Exception:
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

# Mapa de dominios por keywords en el contenido del .md
_DOMAIN_KEYWORDS: List[Tuple[List[str], str]] = [
    (["quantitative", "trading", "strategy", "broker", "order", "signal", "backtest"], "quantitative-analysis"),
    (["risk", "position sizing", "drawdown", "exposure", "kelly"], "risk-management"),
    (["trading", "monitoring", "alert", "live", "market", "operation"], "trading"),
    (["architecture", "system design", "c4", "adr", "enterprise", "roadmap"], "architecture"),
    (["machine learning", "model", "ai", "pipeline", "llm", "training", "inference"], "ai-ml"),
    (["api", "endpoint", "software", "full-stack", "microservice", "backend"], "software-engineering"),
    (["ui", "frontend", "dashboard", "component", "visualization"], "frontend"),
    (["data", "schema", "migration", "model", "database", "etl"], "data-engineering"),
    (["devops", "ci/cd", "docker", "kubernetes", "deploy", "infrastructure"], "devops"),
    (["security", "vulnerability", "compliance", "audit", "secret", "hardening"], "security"),
    (["test", "quality", "coverage", "qa", "gate", "regression"], "quality"),
    (["documentation", "docs", "manual", "technical writing", "readme"], "documentation"),
    (["mobile", "ios", "android", "app", "react native", "flutter"], "mobile"),
    (["requirements", "analysis", "feasibility", "proposal", "user story"], "requirements"),
    (["context", "prompt", "token", "rag", "budget"], "context-engineering"),
    (["tool", "mcp", "server", "json-rpc"], "tool-mcp"),
    (["evolve", "improvement", "cognition", "experiment", "evolution"], "evolve"),
    (["project manager", "planning", "delegate", "coordinate", "roadmap"], "project-management"),
]

# Mapa de capacidades por keywords en el contenido
_CAPABILITY_KEYWORDS: List[Tuple[str, str]] = [
    # software-engineer
    (r"\bapi\b", "api_development"),
    (r"\bendpoint\b", "api_development"),
    (r"\bfull.?stack\b", "full_stack"),
    (r"\bmicroservice", "microservices"),
    (r"\bci/cd\b", "ci_cd"),
    (r"\btesting\b", "testing"),
    (r"\brefactor", "refactoring"),
    # security-engineer
    (r"\bsecurity\b", "security_audit"),
    (r"\bvulnerabilit", "vulnerability_scan"),
    (r"\bcompliance\b", "compliance_check"),
    (r"\bthreat\b", "threat_modeling"),
    (r"\bhardening\b", "hardening"),
    # data-architect
    (r"\bschema\b", "data_modeling"),
    (r"\bmigration", "migration_design"),
    (r"\betl\b", "etl_pipeline"),
    (r"\bdatabase\b", "schema_design"),
    # devops-sre
    (r"\bdocker\b", "docker_kubernetes"),
    (r"\bkubernetes\b", "docker_kubernetes"),
    (r"\bci/cd\b", "ci_cd_pipeline"),
    (r"\bmonitoring\b", "monitoring"),
    (r"\bobservability\b", "observability"),
    (r"\bterraform\b", "infrastructure_as_code"),
    # ai-engineer
    (r"\bmachine learning\b", "ml_pipeline"),
    (r"\bmodel\b", "model_training"),
    (r"\bllm\b", "llm_ops"),
    (r"\binference\b", "inference_optimization"),
    (r"\bfeature engineering\b", "feature_engineering"),
    # quant-developer
    (r"\bstrateg", "strategy_implementation"),
    (r"\border\b", "order_execution"),
    (r"\bbroker\b", "broker_integration"),
    (r"\bbacktest", "backtesting"),
    # frontend-engineer
    (r"\bui\b", "ui_development"),
    (r"\bdashboard\b", "dashboard"),
    (r"\bvisualization\b", "visualization"),
    (r"\bcomponent\b", "component_design"),
    # general
    (r"\bdocumentation\b", "documentation"),
    (r"\bquality\b", "quality_assurance"),
    (r"\bplan", "planning"),
    (r"\brisk\b", "risk_assessment"),
]


def _infer_from_content(filename_stem: str, content: str) -> Dict[str, Any]:
    """
    Infiere nombre, dominio, triggers y capacidades desde el filename y contenido.
    
    Args:
        filename_stem: Nombre del archivo sin extensión (e.g., "software-engineer")
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

    # Inferir triggers: primeras líneas de contenido relevantes
    triggers: List[str] = []
    trigger_patterns = [
        r"@(\w[\w-]*)",           # @rol mentions
        r"!(\w[\w-]*)",           # !comandos
        r"(?:cuando|when|trigger)\s*(?:\:|on)\s*(.+?)[\n\.]",
    ]
    for pattern in trigger_patterns:
        for match in re.finditer(pattern, content):
            triggers.append(match.group(1).strip())

    # Inferir capacidades desde keywords
    capabilities: List[str] = []
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

    # Inferir descripción: primera línea después del título
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

def parse_agent_profile(md_file: Path) -> Optional[Dict[str, Any]]:
    """
    Parsea un archivo .md de agente y extrae su perfil.
    
    Primero intenta leer el perfil pre-compilado (.agent.min.md) si existe,
    que ahorra ~40-60% de tokens. Si no, lee el archivo .md completo.
    Luego parsea frontmatter YAML; si no existe, infiere desde filename y contenido.
    
    Args:
        md_file: Ruta al archivo .md del agente
    
    Returns:
        Dict con name, domain, triggers, capabilities, aliases, description
        o None si el archivo no es un perfil válido.
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


# ---------------------------------------------------------------------------
# Recursive agent discovery
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def discover_agents_recursive(agents_dir: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Descubre agentes recursivamente desde .opencode/agents/.
    
    Usa Path.rglob() para encontrar recursivamente todos los archivos .md
    y extrae sus perfiles. Los resultados se cachean con lru_cache para
    evitar lecturas repetidas de disco.
    
    Args:
        agents_dir: Directorio donde buscar (default: .opencode/agents/)
    
    Returns:
        Dict[str, Dict] con nombre del agente → perfil
        Cada perfil contiene: name, domain, triggers, capabilities, aliases, description
    """
    agents: Dict[str, Dict[str, Any]] = {}
    
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


# ---------------------------------------------------------------------------
# Alias resolution
# ---------------------------------------------------------------------------

def build_alias_map(agents: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    """
    Construye un mapa de alias → nombre canónico desde los agentes descubiertos.
    
    Incluye alias explícitos del frontmatter y alias inferidos por convención.
    
    Args:
        agents: Dict de agentes descubiertos
    
    Returns:
        Dict[str, str] con alias → nombre canónico del agente
    """
    alias_map: Dict[str, str] = {}
    
    for name, info in agents.items():
        # Alias explícitos del frontmatter
        for alias in info.get("aliases", []):
            alias_map[alias.lower()] = name
        
        # Alias por convención: parte antes del primer guión
        # (e.g., "software-engineer" → "software")
        # pero solo si no hay conflicto
        primary = name.split("-")[0]
        if primary != name and primary not in alias_map:
            alias_map[primary] = name
    
    # Aliases hardcodeados para compatibilidad (nunca deben faltar)
    hardcoded_aliases = {
        "pm": "project-manager",
        "swe": "software-engineer",
        "sec": "security-engineer",
        "qa": "quality-gate",
        "data": "data-architect",
        "devops": "devops-sre",
        "frontend": "frontend-engineer",
        "mobile": "mobile-engineer",
        "ai": "ai-engineer",
        "docs": "documentation-specialist",
        "ra": "requirements-analyst",
        "architect": "enterprise-architect",
        "quant": "quant-developer",
        "scientist": "quant-scientist",
        "risk": "risk-manager",
        "ops": "trading-operations",
        "context": "context-engineer",
        "mcp": "tool-mcp-engineer",
    }
    for alias, name in hardcoded_aliases.items():
        if alias not in alias_map:
            alias_map[alias] = name
    
    return alias_map


def resolve_agent_name(alias_or_name: str, agents: Optional[Dict[str, Any]] = None) -> str:
    """
    Resuelve un alias o nombre a su nombre canónico de agente.
    
    Args:
        alias_or_name: Alias (@pm, @swe) o nombre ("project-manager")
        agents: Dict de agentes descubiertos (opcional, auto-descubre si es None)
    
    Returns:
        Nombre canónico del agente, o string vacío si no se encuentra.
    """
    if agents is None:
        agents = discover_agents_recursive()
    
    key = alias_or_name.lower().replace("-", "_")
    
    # Búsqueda directa
    if alias_or_name in agents:
        return alias_or_name
    
    # Construir alias map
    alias_map = build_alias_map(agents)
    
    return alias_map.get(key, "")


# ---------------------------------------------------------------------------
# Capability & Domain helpers
# ---------------------------------------------------------------------------

def get_all_capabilities(agents: Optional[Dict[str, Any]] = None) -> Dict[str, List[str]]:
    """
    Retorna un dict con nombre de agente → lista de capacidades.
    
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


def get_agent_for_domain(domain: str, agents: Optional[Dict[str, Any]] = None) -> str:
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


def list_agents(agents: Optional[Dict[str, Any]] = None) -> List[str]:
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


def build_intent_map(agents: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """
    Construye un mapa de keyword → agente desde los triggers de cada agente.
    
    Cada trigger en el frontmatter del agente se convierte en una entrada
    en el mapa de intents.
    
    Args:
        agents: Dict de agentes (auto-descubre si es None)
    
    Returns:
        Dict[str, str] con keyword → nombre de agente
    """
    if agents is None:
        agents = discover_agents_recursive()
    
    intent_map: Dict[str, str] = {}
    for name, info in agents.items():
        for trigger in info.get("triggers", []):
            trigger_lower = trigger.lower().strip()
            if trigger_lower:
                intent_map[trigger_lower] = name
    
    return intent_map
