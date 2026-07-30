"""
SkillBundler — Dynamic Agent Composition from Skill Registry.

Implementacion del patron SIGMA (Skill-Incidence Graphs, arXiv:2606.19758):
Agentes como bundles de skills reusables, compuestos dinamicamente segun la tarea.
+2.06 pts vs CARD, robusto a skill libraries no vistas (drop solo 0.96 pts).

Usage:
    bundler = SkillBundler()
    agents = bundler.compose("Desarrollar API REST en Rust con autenticacion JWT")
    # → [AgentConfig(name="builder", skills=["rust-lang", "architecture", "security-audit"]), ...]
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_SKILL_REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / ".opencode" / "skills" / "skills_registry.yaml"


# ---------------------------------------------------------------------------
# Skill to Agent Mapping (SIGMA incidence matrix)
# ---------------------------------------------------------------------------

# Mapa de skills → agente primario que deberia ejecutarlos
SKILL_TO_AGENT: Dict[str, str] = {
    "alpha-research": "scientist",
    "evolve": "evolve",
    "healthtech": "builder",
    "hedgefund": "scientist",
    "legal-doc": "scientist",
    "math-doc": "scientist",
    "pos-retail": "builder",
    "quant-trading": "scientist",
    "risk-execution": "guardian",
    "science-doc": "scientist",
    "frontend-uiux": "builder",
    "rust-lang": "builder",
    "architecture": "scientist",
    "responsive-ui": "builder",
    "data-science": "scientist",
    "security-audit": "guardian",
}

# Mapa de dominios → skills relevantes
DOMAIN_SKILLS: Dict[str, List[str]] = {
    "web": ["frontend-uiux", "responsive-ui", "security-audit", "rust-lang"],
    "api": ["architecture", "rust-lang", "security-audit", "data-science"],
    "data": ["data-science", "alpha-research", "architecture"],
    "frontend": ["frontend-uiux", "responsive-ui", "security-audit"],
    "backend": ["rust-lang", "architecture", "data-science", "security-audit"],
    "mobile": ["frontend-uiux", "responsive-ui", "security-audit"],
    "security": ["security-audit", "architecture"],
    "architecture": ["architecture", "rust-lang"],
    "trading": ["quant-trading", "alpha-research", "risk-execution"],
    "research": ["alpha-research", "science-doc", "data-science"],
    "legal": ["legal-doc", "science-doc"],
    "health": ["healthtech", "data-science", "security-audit"],
    "retail": ["pos-retail", "responsive-ui", "security-audit"],
    "devops": ["rust-lang", "security-audit"],
    "general": ["architecture", "security-audit", "data-science", "rust-lang"],
}

# Palabras clave para deteccion de dominio
DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "web": ["pagina web", "sitio web", "website", "http server"],
    "api": ["api", "endpoint", "graphql", "grpc", "microservice"],
    "data": ["data", "datos", "analisis", "pandas", "sklearn", "numpy", "analytics", "machine learning", "deep learning"],
    "frontend": ["frontend", "react", "vue", "svelte", "angular", "landing page", "componente ui"],
    "backend": ["backend", "server", "database", "servicio backend"],
    "mobile": ["mobile", "app ios", "app android", "react native", "flutter"],
    "security": ["security", "seguridad", "owasp", "autenticacion", "harden"],
    "architecture": ["arquitectura", "ddd", "domain driven", "clean architecture", "hexagonal"],
    "trading": ["trading", "quant", "estrategia trading", "mercado financiero"],
    "research": ["research", "investigacion", "paper", "estudio academico"],
    "legal": ["legal", "juridico", "contrato", "norma legal", "regulacion"],
    "health": ["health-record", "salud", "hospital", "paciente", "hipaa"],
    "retail": ["retail", "punto de venta", "pos", "tienda", "inventario", "facturacion"],
    "devops": ["devops", "ci/cd", "deploy", "kubernetes", "docker", "infraestructura"],
}


@dataclass
class AgentConfig:
    """
    Configuracion de un agente compuesto dinamicamente desde skills.
    
    Attributes:
        name: Nombre del agente (builder, scientist, guardian, evolve).
        lead_skill: Skill principal que define el proposito del agente.
        bundled_skills: Skills adicionales que el agente debe cargar.
        domain: Dominio detectado de la tarea.
    """
    name: str
    lead_skill: str
    bundled_skills: List[str]
    domain: str


class SkillBundler:
    """
    Componedor de agentes desde skills (patron SIGMA).
    
    Dado un texto de tarea, detecta el dominio, selecciona skills relevantes,
    y los agrupa en configuraciones de agentes optimas.
    """

    def __init__(self, registry_path: Optional[Path] = None):
        """
        Args:
            registry_path: Ruta al skills_registry.yaml. Por defecto busca en .opencode/skills/.
        """
        self._registry_path = registry_path or _SKILL_REGISTRY_PATH
        self._skills: List[Dict[str, Any]] = []
        self._load_registry()

    def _load_registry(self) -> None:
        """Cargar skills desde el registro YAML."""
        if not self._registry_path.exists():
            return
        try:
            with open(self._registry_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self._skills = data.get("skills", [])
        except Exception:
            self._skills = []

    def detect_domain(self, task: str) -> str:
        """
        Detectar el dominio principal de una tarea por palabras clave.

        Args:
            task: Descripcion de la tarea.

        Returns:
            Dominio detectado (web, api, data, frontend, backend, etc.)
        """
        task_lower = task.lower()
        scores: Dict[str, float] = {}
        
        for domain, keywords in DOMAIN_KEYWORDS.items():
            score = 0.0
            for kw in keywords:
                if kw in task_lower:
                    # Palabras mas largas = mas especificas = mayor peso
                    score += len(kw) / 10.0
            if score > 0:
                scores[domain] = score
        
        if not scores:
            return "general"
        
        return max(scores, key=scores.get)

    def select_skills(self, domain: str, task: Optional[str] = None) -> List[str]:
        """
        Seleccionar skills relevantes para un dominio.

        Args:
            domain: Dominio detectado.
            task: Tarea opcional para filtrado adicional.

        Returns:
            Lista de nombres de skills ordenados por relevancia.
        """
        skills = DOMAIN_SKILLS.get(domain, DOMAIN_SKILLS["general"]).copy()
        
        # Filtro adicional por keywords en la tarea
        if task:
            task_lower = task.lower()
            # Skills adicionales si la tarea menciona temas especificos
            if "test" in task_lower or "testing" in task_lower:
                if "security-audit" not in skills:
                    skills.append("security-audit")
            if "doc" in task_lower or "documentacion" in task_lower:
                for s in ["science-doc", "legal-doc"]:
                    if s not in skills:
                        skills.append(s)
        
        return skills

    def compose(
        self,
        task: str,
        available_agents: Optional[List[str]] = None,
    ) -> List[AgentConfig]:
        """
        Componer configuraciones de agentes desde una descripcion de tarea.

        Implementa el patron SIGMA: predice una matriz de incidencia
        skills-agentes y compone bundles de skills para cada agente.

        Args:
            task: Descripcion de la tarea a realizar.
            available_agents: Agentes disponibles (default: builder, scientist, guardian, evolve).

        Returns:
            Lista de AgentConfig con agentes compuestos y sus skills asignados.
        """
        if available_agents is None:
            available_agents = ["builder", "scientist", "guardian", "evolve"]

        domain = self.detect_domain(task)
        selected_skills = self.select_skills(domain, task)

        # Construir matriz de incidencia skills → agentes
        agent_bundles: Dict[str, List[str]] = {a: [] for a in available_agents}
        for skill in selected_skills:
            primary_agent = SKILL_TO_AGENT.get(skill)
            if primary_agent and primary_agent in agent_bundles:
                agent_bundles[primary_agent].append(skill)

        # Crear configs solo para agentes con skills asignados
        configs = []
        for agent, skills in agent_bundles.items():
            if not skills:
                # Asignar skill generico segun el agente
                default_skills = {
                    "builder": ["rust-lang"],
                    "scientist": ["architecture"],
                    "guardian": ["security-audit"],
                    "evolve": [],
                }
                skills = default_skills.get(agent, [])
            
            lead = skills[0] if skills else ""
            configs.append(AgentConfig(
                name=agent,
                lead_skill=lead,
                bundled_skills=skills,
                domain=domain,
            ))

        return configs

    def get_skill_description(self, skill_name: str) -> str:
        """Obtener descripcion de un skill desde el registry."""
        for s in self._skills:
            if s.get("name") == skill_name:
                return s.get("description", "")
        return ""

    def list_skills(self) -> List[str]:
        """Listar todos los skills disponibles."""
        return [s.get("name", "") for s in self._skills]

    def list_domains(self) -> List[str]:
        """Listar todos los dominios soportados."""
        return list(DOMAIN_SKILLS.keys())
