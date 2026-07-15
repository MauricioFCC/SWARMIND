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

import os
import re
import sys
from typing import Any, Dict, List, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from harness.orchestrator.task_manager import TaskManager

# Importar descubrimiento recursivo de agentes
# (reemplaza _DEFAULT_CAPABILITIES, _DEFAULT_INTENT_AGENTS, _DEFAULT_DOMAIN_MAP)
from harness.orchestrator.agent_discovery import (
    discover_agents_recursive,
    build_intent_map,
    get_all_capabilities,
    get_agent_for_domain as discovery_get_agent_for_domain,
    resolve_agent_name as discovery_resolve_agent_name,
    list_agents as discovery_list_agents,
)


def _find_routing_rules_path() -> str:
    base = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    candidate = os.path.join(base, ".opencode", "config", "routing_rules.yaml")
    if os.path.isfile(candidate):
        return candidate
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
            sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
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
        for keyword, agent in sorted(
            self._intent_map.items(), key=lambda x: -len(x[0])
        ):
            if keyword in text:
                return agent
        return ""

    def auto_route(self, message: str) -> str:
        """
        Auto-detecta el rol universal a partir del contenido del mensaje.
        
        NO requiere @. Analiza keywords y enruta al rol universal apropiado.
        Si no hay match, el coordinador maneja la tarea directamente.
        
        Orden de precedencia:
          1. Evolve (auto-mejora del sistema)
          2. Scientist (investigación, papers, AI/ML, patrones)
          3. Guardian (calidad, seguridad, riesgo, docs)
          4. Builder (toda implementación: Rust, Go, Python, Web, Mobile, Trading)
          5. Coordinator (default — analiza y delega)
        """
        text = message.lower()
        
        # Universal role routing by intent keywords
        # Ordenado por especificidad: los más específicos primero
        
        # @evolve: auto-mejora del sistema
        evolve_patterns = ["!evolve", "evolve", "skill improvement", "cognition",
                          "self-improve", "auto-improve"]
        for pat in evolve_patterns:
            if pat in text:
                return "evolve"
        
        # @scientist: investigación, arquitectura, AI/ML, patrones
        scientist_patterns = ["research", "paper", "architecture", "pattern",
                             "methodology", "algorithm", "study", "ml model",
                             "deep learning", "neural", "train model",
                             "experiment design", "statistical", "causal",
                             "literature", "survey", "novel approach",
                             "system design", "trade-off", "capacity plan",
                             "arquitectura", "investigacion", "patron de diseno",
                             "modelo ml", "modelo ia", "entrenar modelo",
                             "analisis", "experimento", "validacion"]
        for pat in scientist_patterns:
            if pat in text:
                return "scientist"
        
        # @guardian: calidad, seguridad, riesgo, docs
        # NOTA: va ANTES que builder para que "documentacion" no sea atrapado por "api"
        guardian_patterns = ["test", "testing", "security", "audit", "risk",
                            "documentation", "documentacion", "monitor", "monitoring",
                            "quality gate", "code review", "lint", "coverage",
                            "hardening", "compliance", "observability", "alert",
                            "calidad", "seguridad", "auditoria", "riesgo",
                            "cobertura", "revision de codigo"]
        for pat in guardian_patterns:
            if pat in text:
                return "guardian"
        
        # @builder: toda implementación
        builder_patterns = ["implement", "build", "create", "develop", "code",
                           "api", "endpoint", "rust", "go lang", "golang",
                           "python", "typescript", "web", "frontend", "backend",
                           "fullstack", "mobile", "android", "ios", "app",
                           "server", "database", "sql", "deploy", "docker",
                           "kubernetes", "ci/cd", "trading", "strategy",
                           "algorithm", "library", "refactor", "migrate",
                           "cli tool", "microservice", "rest api", "graphql"]
        for pat in builder_patterns:
            if pat in text:
                return "builder"
        
        # Default: coordinator (analiza y delega)
        return "coordinator"

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
