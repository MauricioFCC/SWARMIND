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
from typing import Any

import yaml

from harness.orchestrator.keyword_match import match_keywords, normalize
from harness.orchestrator.prompt_sanitizer import sanitize_task

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_SKILL_REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / ".opencode" / "skills" / "skills_registry.yaml"

#: Similitud Jaccard de tokens del NOMBRE a partir de la cual dos skills se
#: consideran near-duplicates (misma habilidad con nombre variado).
_NEAR_DUPLICATE_THRESHOLD = 0.9


def _name_tokens(name: str) -> frozenset[str]:
    """Tokeniza el nombre de un skill (normalizado) para comparar por Jaccard.

    Args:
        name: Nombre del skill (p. ej. ``"security-audit"``).

    Returns:
        Conjunto de tokens normalizados; ``frozenset()`` si el nombre es vacio.
    """
    return frozenset(normalize(name).split())


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """Calcula la similitud Jaccard entre dos conjuntos de tokens.

    Args:
        left: Primer conjunto de tokens.
        right: Segundo conjunto de tokens.

    Returns:
        ``|interseccion| / |union|`` en ``[0.0, 1.0]``; ``1.0`` si ambos son
        vacios.
    """
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _deduplicate_near_duplicates(names: list[str]) -> list[str]:
    """Elimina skills near-duplicadas conservando la canonica (la primera).

    Args:
        names: Nombres de skills en orden canonico (registry/dominio).

    Returns:
        Lista sin near-duplicates (Jaccard de tokens del nombre
        ``>= _NEAR_DUPLICATE_THRESHOLD``), preservando el orden de entrada.
    """
    kept: list[str] = []
    kept_tokens: list[frozenset[str]] = []
    for name in names:
        tokens = _name_tokens(name)
        is_duplicate = any(
            _jaccard(tokens, seen) >= _NEAR_DUPLICATE_THRESHOLD for seen in kept_tokens
        )
        if is_duplicate:
            continue
        kept.append(name)
        kept_tokens.append(tokens)
    return kept


# ---------------------------------------------------------------------------
# Skill to Agent Mapping (SIGMA incidence matrix)
# ---------------------------------------------------------------------------

# Mapa de skills → agente primario que deberia ejecutarlos
SKILL_TO_AGENT: dict[str, str] = {
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
    "data-science": "scientist",
    "security-audit": "guardian",
    "agent-rigor": "guardian",
    "atdd-spec": "builder",
    "behavioral-economics": "scientist",
    "business-strategy": "scientist",
    "communication": "builder",
    "creative-design": "builder",
    "devops-infra": "builder",
    "diagram-design": "builder",
    "education": "scientist",
    "ethics": "guardian",
    "linguistics": "scientist",
    "physical-sciences": "scientist",
    "process-over-tools": "coordinator",
    "project-management": "builder",
    "psychology": "scientist",
    "risk-intelligence": "scientist",
    "sociology": "scientist",
    "sustainability": "scientist",
    "swarm-release-ops": "builder",
}

# Mapa de dominios → skills relevantes
DOMAIN_SKILLS: dict[str, list[str]] = {
    "web": ["frontend-uiux", "security-audit", "rust-lang"],
    "api": ["architecture", "rust-lang", "security-audit", "data-science"],
    "data": ["data-science", "alpha-research", "architecture"],
    "frontend": ["frontend-uiux", "security-audit"],
    "backend": ["rust-lang", "architecture", "data-science", "security-audit"],
    "mobile": ["frontend-uiux", "security-audit"],
    "security": ["security-audit", "architecture"],
    "architecture": ["architecture", "rust-lang"],
    "trading": ["quant-trading", "alpha-research", "risk-execution"],
    "research": ["alpha-research", "science-doc", "data-science"],
    "legal": ["legal-doc", "science-doc"],
    "health": ["healthtech", "data-science", "security-audit"],
    "retail": ["pos-retail", "frontend-uiux", "security-audit"],
    "devops": ["rust-lang", "security-audit", "devops-infra", "swarm-release-ops"],
    "quality": ["agent-rigor", "atdd-spec", "security-audit"],
    "general": ["architecture", "security-audit", "data-science", "rust-lang"],
}

# Palabras clave para deteccion de dominio
DOMAIN_KEYWORDS: dict[str, list[str]] = {
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
    "quality": ["quality gate", "mutation testing", "code review", " QA ", " TDD ", "cobertura"],
}

#: Keywords de testing que agregan seguridad a cualquier dominio.
_TASK_TEST_KEYWORDS: tuple[str, ...] = ("test", "testing", "tests")
#: Keywords que agregan skills de documentacion. Matching por frontera de palabra:
#: "doc" NO matchea "docker" (falso positivo previo por substring).
_TASK_DOC_KEYWORDS: tuple[str, ...] = ("doc", "docs", "documentacion")
#: Skills de documentacion disparadas por `_TASK_DOC_KEYWORDS`.
_TASK_DOC_SKILLS: tuple[str, ...] = ("science-doc", "legal-doc")


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
    bundled_skills: list[str]
    domain: str


class SkillBundler:
    """
    Componedor de agentes desde skills (patron SIGMA).
    
    Dado un texto de tarea, detecta el dominio, selecciona skills relevantes,
    y los agrupa en configuraciones de agentes optimas.
    """

    def __init__(self, registry_path: Path | None = None):
        """
        Args:
            registry_path: Ruta al skills_registry.yaml. Por defecto busca en .opencode/skills/.
        """
        self._registry_path = registry_path or _SKILL_REGISTRY_PATH
        self._skills: list[dict[str, Any]] = []
        self._load_registry()

    def _load_registry(self) -> None:
        """Cargar skills desde el registro YAML y resolver rutas faltantes."""
        if not self._registry_path.exists():
            return
        try:
            with open(self._registry_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self._skills = data.get("skills", [])
            self._resolve_missing_paths()
        except Exception:  # noqa: BLE001
            self._skills = []

    def _resolve_missing_paths(self) -> None:
        """Completa el campo ``path`` de cada skill con ``<skills>/<name>/SKILL.md``.

        WHAT: si una entrada del registry no declara ``path``, lo resuelve a
        ``.opencode/skills/<name>/SKILL.md`` cuando el archivo existe. WHY: el
        registry curado no trae ``path``, de modo que aguas abajo el ``content``
        del skill quedaba vacio. WHERE: ``SkillBundler`` y consumidores del
        registry.

        Returns:
            None. Muta ``self._skills`` in-place (agrega la clave ``path``).
        """
        skills_root = self._registry_path.parent
        for skill in self._skills:
            if skill.get("path"):
                continue
            candidate = skills_root / str(skill.get("name", "")) / "SKILL.md"
            if candidate.exists():
                skill["path"] = str(candidate)

    def detect_domain(self, task: str) -> str:
        """
        Detectar el dominio principal de una tarea por palabras clave.

        WHAT: puntua cada dominio con las keywords que matchean por frontera de
        palabra (`keyword_match`), ponderando por longitud (mas especifica = mas
        peso). WHY: el matching por substring producia falsos positivos ("api" en
        "capital", "pos" en "position", "doc" en "docker"). WHERE: coordinator y
        `compose`.

        Args:
            task: Descripcion de la tarea.

        Returns:
            Dominio detectado (web, api, data, frontend, backend, etc.), o
            "general" si ninguna keyword matchea.
        """
        safe_task = sanitize_task(task)
        scores: dict[str, float] = {}
        for domain, keywords in DOMAIN_KEYWORDS.items():
            matched = match_keywords(safe_task, keywords)
            if matched:
                # Palabras mas largas = mas especificas = mayor peso
                scores[domain] = sum(len(kw) for kw in matched) / 10.0

        if not scores:
            return "general"

        return max(scores, key=lambda name: scores[name])

    def select_skills(self, domain: str, task: str | None = None) -> list[str]:
        """
        Seleccionar skills relevantes para un dominio.

        WHAT: parte de las skills curadas del dominio y agrega las de testing y
        documentacion solo si la tarea las menciona como palabra completa
        (`keyword_match`), preservando el orden determinista y sin duplicados.
        WHY: el filtro por substring inyectaba skills de documentacion ante
        "docker" ("doc" es substring de "docker").

        ABSTENCION: un dominio desconocido devuelve ``[]`` en lugar de fabricar la
        lista "general"; el dominio explicito "general" sigue siendo un mapeo
        curado valido.

        Args:
            domain: Dominio detectado.
            task: Tarea opcional para filtrado adicional.

        Returns:
            Lista de skills ordenadas; ``[]`` si el dominio es desconocido
            (contrato de abstencion).
        """
        skills = list(DOMAIN_SKILLS.get(domain, ()))
        if not skills:
            return []

        if task:
            if match_keywords(task, _TASK_TEST_KEYWORDS) and "security-audit" not in skills:
                skills.append("security-audit")
            if match_keywords(task, _TASK_DOC_KEYWORDS):
                for skill in _TASK_DOC_SKILLS:
                    if skill not in skills:
                        skills.append(skill)

        return _deduplicate_near_duplicates(skills)

    def compose(
        self,
        task: str,
        available_agents: list[str] | None = None,
    ) -> list[AgentConfig]:
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
        agent_bundles: dict[str, list[str]] = {a: [] for a in available_agents}
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

    def list_skills(self) -> list[str]:
        """Listar todos los skills disponibles sin near-duplicates."""
        names = [s.get("name", "") for s in self._skills]
        return _deduplicate_near_duplicates(names)

    def list_domains(self) -> list[str]:
        """Listar todos los dominios soportados."""
        return list(DOMAIN_SKILLS.keys())
