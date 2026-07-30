"""Delegation engine with UNIVERSAL auto-routing.

CONSOLIDACIÓN: 21 agentes especializados → 5 roles universales:
  - @coordinator (entry point, auto-detecta y delega)
  - @builder     (toda implementación: Rust, Go, Python, Web, Mobile, Trading, Infra)
  - @scientist   (investigación, papers, AI/ML, arquitectura, patrones)
  - @guardian    (calidad, seguridad, riesgo, docs, operaciones)
  - @evolve      (auto-mejora del sistema)

No requiere @: si escribes "implementa una API en Rust", se detecta
automáticamente y se enruta a @builder. El @ solo es necesario si
quieres forzar un rol específico.

REFACTOR: Reemplaza ~200 líneas de mappings hardcodeados con
descubrimiento recursivo de agentes desde .opencode/agents/*.md.
Ver agent_discovery.py para el patrón recursivo aplicado.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Importar descubrimiento recursivo de agentes
# (reemplaza _DEFAULT_CAPABILITIES, _DEFAULT_INTENT_AGENTS, _DEFAULT_DOMAIN_MAP)
from harness.orchestrator.agent_discovery import (
    build_intent_map,
    discover_agents_recursive,
    get_all_capabilities,
)
from harness.orchestrator.agent_discovery import (
    get_agent_for_domain as discovery_get_agent_for_domain,
)
from harness.orchestrator.agent_discovery import (
    list_agents as discovery_list_agents,
)
from harness.orchestrator.agent_discovery import (
    resolve_agent_name as discovery_resolve_agent_name,
)
from harness.orchestrator.task_manager import TaskManager


def _find_routing_rules_path() -> str:
    base = Path(__file__).resolve().parent.parent.parent
    candidate = base / ".opencode" / "config" / "routing_rules.yaml"
    if candidate.is_file():
        return str(candidate)
    return ""


def _load_yaml_rules(path: str) -> Dict[str, Any]:
    if not HAS_YAML:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data
    except (FileNotFoundError, yaml.YAMLError):
        return {}


class DelegationEngine:
    """Maps tasks and messages to the appropriate agent role.

    Loads routing rules from .opencode/config/routing_rules.yaml and
    integrates with the Router v2 logic when available.

    Los agentes se descubren RECURSIVAMENTE desde .opencode/agents/*.md
    en lugar de usar mappings hardcodeados.
    """

    def __init__(self, task_manager: Optional[TaskManager] = None) -> None:
        """Inicializa la instancia de la clase.

        Descubre agentes recursivamente y carga reglas YAML como override.
        """
        self._task_manager: Optional[TaskManager] = task_manager
        self._routing_rules: Dict[str, Any] = {}

        # Descubrimiento recursivo de agentes (reemplaza ~200 líneas de dicts)
        self._agents = discover_agents_recursive()
        self._intent_map: Dict[str, str] = build_intent_map(self._agents)
        self._capabilities: Dict[str, List[str]] = get_all_capabilities(self._agents)
        self._router_v2: Any = None

        self._load_config()
        self._try_import_router_v2()

    def _load_config(self) -> None:
        """Carga reglas YAML como override sobre el descubrimiento recursivo.

        Las reglas del YAML tienen prioridad sobre los triggers inferidos
        de los archivos .md.
        """
        rules_path = _find_routing_rules_path()
        if not rules_path:
            return

        data = _load_yaml_rules(rules_path)
        if not data:
            return

        self._routing_rules = data

        routing = data.get("routing_rules", data)
        if isinstance(routing, dict):
            intent_rules = routing.get("intent_routing", [])
            for rule in intent_rules:
                agent = rule.get("target_agent", "")
                keywords = rule.get("keywords", [])
                for kw in keywords:
                    self._intent_map[kw.lower()] = agent

            domain_routes = routing.get("domain_routes", [])
            for route in domain_routes:
                domain = route.get("domain", "")
                agents = route.get("agents", [])
                if agents:
                    self._intent_map[f"__domain_{domain}"] = agents[0]

            departments = data.get("departments", {})
            for dept_name, dept_info in departments.items():
                head = dept_info.get("head", "")
                funciones = dept_info.get("funciones", [])
                if head and funciones:
                    if head not in self._capabilities:
                        self._capabilities[head] = []
                    for func in funciones:
                        slug = func.lower().replace(" ", "_").replace("á", "a").replace(
                            "é", "e"
                        ).replace("í", "i").replace("ó", "o").replace("ú", "u")
                        if slug not in self._capabilities[head]:
                            self._capabilities[head].append(slug)

                miembros = dept_info.get("miembros", [])
                for miembro in miembros:
                    if miembro in self._capabilities:
                        for func in funciones:
                            slug = func.lower().replace(" ", "_").replace("á", "a").replace(
                                "é", "e"
                            ).replace("í", "i").replace("ó", "o").replace("ú", "u")
                            if slug not in self._capabilities[miembro]:
                                self._capabilities[miembro].append(slug)

    def _try_import_router_v2(self) -> None:
        try:
            from opencode.core import router_v2  # type: ignore
            self._router_v2 = router_v2
        except ImportError:
            sys.path.insert(1, str(Path(__file__).resolve().parent.parent.parent))
            try:
                from opencode.core import router_v2  # type: ignore
                self._router_v2 = router_v2
            except ImportError:
                pass

    def delegate(self, task: Any) -> str:
        """Assign a task to the most appropriate agent based on its content.

        Args:
            task: A Task object (or dict-like) with at least title and description.

        Returns:
            The agent name (string) that the task was delegated to.
        """
        title = ""
        description = ""
        if hasattr(task, "to_dict"):
            data = task.to_dict()
            title = data.get("title", "")
            description = data.get("description", "")
        elif isinstance(task, dict):
            title = task.get("title", "")
            description = task.get("description", "")
        else:
            title = getattr(task, "title", "")
            description = getattr(task, "description", "")

        combined = f"{title} {description}".lower()

        agent = self._match_intent(combined)
        if agent:
            return agent

        return "coordinator"

    def _match_intent(self, text: str) -> str:
        """Match por keyword con scoring (mas especifico = mayor peso)."""
        scores: dict[str, float] = {}
        for keyword, agent in self._intent_map.items():
            if keyword in text:
                # Mas larga la keyword = mas especifica = mas peso
                weight = len(keyword) / max(len(text), 1)
                scores[agent] = scores.get(agent, 0) + weight
        if scores:
            return max(scores, key=scores.get)
        return ""

    def auto_route(self, message: str) -> str:
        """
        Auto-detecta el rol universal a partir del contenido del mensaje.
        
        NO requiere @. Analiza keywords con scoring ponderado y enruta
        al agente mas especifico. Si no hay match, el coordinador maneja.
        
        Orden de precedencia (por scoring, no por orden de busqueda):
          1. Evolve (auto-mejora del sistema)
          2. Scientist (investigacion, papers, AI/ML, patrones)
          3. Guardian (calidad, seguridad, riesgo, docs)
          4. Builder (toda implementacion)
          5. Coordinator (default)
        """
        text = message.lower()
        scores: dict[str, float] = {"coordinator": 0.0}

        # Scoring ponderado: cada keyword suma segun su longitud
        # Se usa word boundary para evitar falsos positivos parciales
        
        def word_in_text(word: str) -> bool:
            """Check if word appears as whole word in text."""
            return ' ' + word + ' ' in ' ' + text + ' '

        # evolve: auto-mejora del sistema
        for pat in ["!evolve", "asi-evolve", "self-improve", "auto-improve",
                    "skill improvement", "cognition store", "evolve loop",
                    "mejora continua", "auto-mejora", "mejora el sistema",
                    "mejora el rendimiento", "optimiza el skill"]:
            if pat in text:
                scores["evolve"] = scores.get("evolve", 0) + len(pat) * 2

        # scientist: investigacion, arquitectura, experimentos, papers
        for pat in ["research paper", "scientific paper", "literature review",
                    "machine learning", "deep learning", "train model",
                    "experiment design", "statistical validation",
                    "causal inference", "system design",
                    "investigacion", "investiga", "experimento",
                    "patrones de diseno", "patron de diseno",
                    "analisis de datos", "arquitectura del sistema",
                    "arquitectura hexagonal", "trade-off",
                    "algorithm design", "survey paper", "capacity planning",
                    "papers sobre", "articulos sobre", "investiga papers"]:
            if pat in text:
                scores["scientist"] = scores.get("scientist", 0) + len(pat) * 2

        # guardian: calidad, seguridad, riesgo, documentacion, testing
        for pat in ["security audit", "threat model", "code review",
                    "quality gate", "mutation test", "adversarial test",
                    "performance test", "load test", "fuzz test",
                    "hardening", "compliance", "observability",
                    "documentacion tecnica", "technical writing",
                    "auditoria de seguridad", "audita la seguridad",
                    "pruebas de rendimiento", "cobertura de tests",
                    "revision de codigo", "haz una auditoria"]:
            if pat in text:
                scores["guardian"] = scores.get("guardian", 0) + len(pat) * 2

        # builder: implementacion, desarrollo, codigo
        for pat in ["implementa una", "crea un modulo", "crea un frontend",
                    "desarrolla un", "implementa una api", "rest api",
                    "graphql api", "microservicio", "microservice",
                    "database schema", "deploy service",
                    "docker container", "kubernetes deployment",
                    "trading strategy", "market making",
                    "cli tool", "api endpoint", "funcion de ordenamiento",
                    "modulo de autenticacion", "api rest"]:
            if pat in text:
                scores["builder"] = scores.get("builder", 0) + len(pat) * 2

        # Palabras individuales (segundo nivel, menos peso)
        builder_words = ["implement", "create", "build", "code", "api",
                        "rust", "golang", "python", "frontend", "backend",
                        "database", "docker", "deploy", "app"]
        for w in builder_words:
            if word_in_text(w):
                scores["builder"] = scores.get("builder", 0) + len(w)

        # Palabras de scientist (segundo nivel)
        scientist_words = ["research", "paper", "architecture", "pattern",
                          "study", "survey", "analyse", "investiga"]
        for w in scientist_words:
            if word_in_text(w):
                scores["scientist"] = scores.get("scientist", 0) + len(w)

        # Palabras de guardian (segundo nivel)
        guardian_words = ["testing", "security", "audit", "risk", "documentation",
                         "hardening", "coverage", "seguridad", "auditoria",
                         "calidad", "documentacion", "pruebas", "cobertura"]
        for w in guardian_words:
            if w in text.split():
                scores["guardian"] = scores.get("guardian", 0) + len(w)
        # test como palabra corta (match exacto con espacio)
        if " test " in ' ' + text + ' ':
            scores["guardian"] = scores.get("guardian", 0) + 4

        # Elegir el de mayor score
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "coordinator"

    def route_message(self, message: str) -> str:
        """
        Enruta un mensaje al agente apropiado.
        
        Soporta:
          - @rol: mensaje (ruteo explícito)
          - mensaje sin @ (auto-detección por contenido)
          - !comandos (comandos del sistema)
        
        La auto-detección mapea a 5 roles universales:
        coordinator, builder, scientist, guardian, evolve.
        """
        # !comandos van al coordinator (que los procesa directamente)
        if message.startswith("!"):
            return "coordinator"

        # @rol: mensaje — ruteo explícito (backward compatible)
        mentions = re.findall(r"@(\w[\w-]*)", message)
        if mentions:
            for mention in mentions:
                agent = self._resolve_agent_name(mention)
                if agent:
                    return agent

        if self._router_v2 is not None:
            try:
                result = self._router_v2.route_message(message)
                if isinstance(result, dict):
                    return result.get("agent", "coordinator")
                if isinstance(result, str) and result:
                    return result
            except Exception as _exc:
                logger.warning("delegation_engine: %s", _exc)

        # Auto-detección por contenido (NO requiere @)
        return self.auto_route(message)

    def _resolve_agent_name(self, name: str) -> str:
        """Resuelve alias (@pm, @swe) a nombre canónico usando descubrimiento recursivo.

        Delega en agent_discovery.resolve_agent_name() que construye
        el mapa de alias dinámicamente desde los perfiles de agente.
        """
        return discovery_resolve_agent_name(name, self._agents)

    def get_agent_capabilities(self) -> Dict[str, List[str]]:
        """Return a dict mapping each agent name to its list of capabilities."""
        return {k: list(v) for k, v in self._capabilities.items()}

    def get_agent_for_domain(self, domain: str) -> str:
        """Return the primary agent responsible for a given domain."""
        return discovery_get_agent_for_domain(domain, self._agents)

    def list_agents(self) -> List[str]:
        """Return the list of all known agent names."""
        return discovery_list_agents(self._agents)

    def set_task_manager(self, task_manager: TaskManager) -> None:
        """Attach a TaskManager instance after construction."""
        self._task_manager = task_manager

    # ------------------------------------------------------------------
    # Plan-and-Execute integration
    # ------------------------------------------------------------------

    def plan_task(self, message: str) -> "TaskPlan":
        """
        Decompose a user message into a structured execution plan.

        Uses TaskPlanner to produce a DAG of subtasks with dependencies,
        agent assignments, and expected outputs.

        Args:
            message: The user's request.

        Returns:
            A TaskPlan with subtasks organized by dependency level.
        """
        from harness.orchestrator.task_planner import TaskPlanner
        planner = TaskPlanner()
        return planner.decompose(message)

    def route_with_plan(self, message: str) -> Dict:
        """
        Route a message AND return a structured execution plan.

        This is the main entry point for Plan-and-Execute. Instead of just
        returning an agent name, it returns:
          - target_agent: primary agent for this dispatch
          - plan: full TaskPlan with subtasks and DAG levels
          - current_level: subtasks ready for immediate execution
          - plan_summary: human-readable plan overview

        Args:
            message: The user's message.

        Returns:
            Dict with routing + plan information.
        """
        from harness.orchestrator.task_planner import TaskPlanner
        planner = TaskPlanner()
        plan = planner.decompose(message)
        next_level = plan.get_next_level()

        target_agent = self.auto_route(message)

        current_level = []
        for st in next_level:
            current_level.append({
                "id": st.id,
                "agent": st.agent,
                "description": st.description,
                "expected_output": st.expected_output,
                "dependencies": st.dependencies,
            })

        return {
            "target_agent": target_agent,
            "plan": plan,
            "current_level": current_level,
            "plan_summary": plan.get_summary(),
            "session_id": plan.session_id,
        }

    def get_plan_summary(self, message: str) -> str:
        """
        Get a human-readable plan summary without executing anything.

        Useful for showing the user what the system plans to do.

        Args:
            message: The user's request.

        Returns:
            Formatted string with the execution plan.
        """
        plan = self.plan_task(message)
        return plan.get_summary()
