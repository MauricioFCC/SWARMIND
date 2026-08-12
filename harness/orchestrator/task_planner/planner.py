"""Clase ``TaskPlanner`` — descomposición de mensajes en planes DAG.

Extracción mecánica desde ``harness/orchestrator/task_planner.py``
(sin cambios de lógica).

El logger se resuelve vía el paquete en tiempo de llamada
(``import harness.orchestrator.task_planner as _pkg``) manteniendo el nombre
de logger original ``harness.orchestrator.task_planner``.
"""

from __future__ import annotations

from typing import ClassVar

import harness.orchestrator.task_planner as _pkg
from harness.memory_rag.compaction import structured_compact

from .models import SubTask, TaskPlan
from .templates import SUBTASK_TEMPLATES


class TaskPlanner:
    """
    Decomposes user messages into structured execution plans (DAG).

    Usage:
        planner = TaskPlanner()
        plan = planner.decompose("implementa una API REST en Rust")
        for level in plan.get_levels():
            for subtask in level:
                print(f"[{subtask.agent}] {subtask.description}")
    """

    # Mapa de confidence_impact por tipo de template
    _TEMPLATE_CONFIDENCE_IMPACT: ClassVar[dict[str, str]] = {
        "security_audit": "critical",
        "deploy": "critical",
        "implement_api": "high",
        "fix_bug": "critical",
        "docs": "validation",
        "test": "validation",
    }

    def __init__(self) -> None:
        self._counter: int = 0
        self._injector = None  # Lazy import
        self._scope_analyzer = None  # Lazy import

    def _get_injector(self):
        """Lazy import de ContextInjector para evitar circular imports."""
        if self._injector is None:
            from harness.memory_rag.context_injector import ContextInjector
            self._injector = ContextInjector(always_inject=True)
        return self._injector

    def _get_scope_analyzer(self):
        """Lazy import de ScopeAnalyzer para evitar circular imports."""
        if self._scope_analyzer is None:
            from harness.orchestrator.scope_analyzer import ScopeAnalyzer
            self._scope_analyzer = ScopeAnalyzer()
        return self._scope_analyzer

    def decompose(self, message: str) -> TaskPlan:
        """
        Decompose a user message into a structured TaskPlan.

        Strategy:
          1. Detect task type from keywords and patterns
          2. Load matching template (o genera uno dinamico segun alcance)
          3. Customize subtasks based on specifics in message
          4. Assign a session ID

        DYNAMIC SCALING: Si el template detectado es "swarm_default",
        el ScopeAnalyzer determina cuantos builders/guardians lanzar
        segun la cantidad de trabajo detectada en el mensaje.

        Args:
            message: The user's request/message.

        Returns:
            A TaskPlan with subtasks organized for DAG execution.
        """
        import uuid
        msg_lower = message.lower()

        # --- 1. Detect template ---
        template_name, template = self._detect_template(msg_lower)

        # --- 2. Extract specifics from message ---
        specifics = self._extract_specifics(message)

        # Compactar contexto (Token Economics - ADR-0018)
        agent_context = specifics.get("context", "")
        if agent_context and len(agent_context) > 500:
            agent_context = structured_compact(agent_context, budget_ratio=0.6)
            specifics["context"] = agent_context

        # --- 3. DYNAMIC SCALING: si es swarm_default, analizar alcance ---
        if template_name == "swarm_default":
            analyzer = self._get_scope_analyzer()
            scope = analyzer.analyze(message)
            template_name = analyzer.get_template_name(scope)
            subtask_dicts = analyzer.generate_subtasks(scope)
            template = {"description": f"dynamic_{scope.level}", "subtasks": subtask_dicts}

        # --- 4. Build subtasks from template ---
        subtasks: list[SubTask] = []
        idx_to_id: dict[int, str] = {}
        for idx, tpl in enumerate(template["subtasks"]):
            self._counter += 1
            subtask_id = f"st-{self._counter}"
            idx_to_id[idx] = subtask_id
            # dep value is the template index of the dependency
            dep_ids = [idx_to_id[dep] for dep in tpl["deps"] if dep in idx_to_id]

            description = self._customize_description(
                tpl["description"], specifics
            )

            # Inyectar estandares en la descripcion (ContextInjector)
            injector = self._get_injector()
            injected_desc = injector.inject(description, agent_role=tpl["agent"])

            subtasks.append(SubTask(
                id=subtask_id,
                agent=tpl["agent"],
                description=injected_desc,
                dependencies=dep_ids,
                expected_output=tpl["expected_output"],
                context_hint=specifics.get("context", tpl.get("context_hint", "")),
                confidence_impact=self._TEMPLATE_CONFIDENCE_IMPACT.get(
                    template_name, tpl.get("confidence_impact", "neutral")
                ),
            ))

        plan = TaskPlan(
            session_id=str(uuid.uuid4())[:8],
            original_message=message,
            subtasks=subtasks,
            template_name=template_name,
        )

        _pkg.logger.info(
            "Plan %s [%s]: %s — %d subtasks en %d niveles",
            plan.session_id, template_name, template["description"],
            len(plan.subtasks), len(plan.get_levels()),
        )

        return plan

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _detect_template(self, msg_lower: str) -> tuple:
        """
        Detect the best matching template for a message.

        OPTIMIZACION SWISS WATCH:
        - "swarm_default" tiene prioridad para tareas de implementacion (maximo paralelismo)
        - Si hay keywords claras de implementacion, usa SWARM
        - Fallback a general template que tambien tiene multi-agente paralelo

        Returns:
            Tuple of (template_name, template_dict).
        """
        best_score = 0
        best_name = "general"
        best_template = SUBTASK_TEMPLATES["general"]

        # Fase 1: Buscar template especifico (fix_bug, research, etc.)
        # Umbral ALTO (>3) para que solo tareas MUY especificas activen templates concretos.
        # Por defecto, TODO va a swarm_default (que escala dinamicamente segun alcance).
        for name, tpl in SUBTASK_TEMPLATES.items():
            triggers = tpl.get("triggers", [])
            if not triggers or name in ("swarm_default", "general"):
                continue
            score = sum(1 for t in triggers if t in msg_lower)
            # Umbral 3+ keywords para template especifico (antes era 2)
            if score >= 3:
                _pkg.logger.debug("Specific template %s selected (score=%d)", name, score)
                return name, tpl

        # Fase 2: Si no hay template especifico -> SWARM DINAMICO (escala segun alcance)
        # Cualquier mensaje con al menos 1 keyword de implementacion activa el escalado
        swarm_triggers = SUBTASK_TEMPLATES["swarm_default"].get("triggers", [])
        swarm_score = sum(1 for t in swarm_triggers if t in msg_lower)
        if swarm_score >= 1:  # Solo 1 keyword y va a dinamico
            _pkg.logger.debug("SWARM DINAMICO (score=%d)", swarm_score)
            return "swarm_default", SUBTASK_TEMPLATES["swarm_default"]

        for name, tpl in SUBTASK_TEMPLATES.items():
            triggers = tpl.get("triggers", [])
            if not triggers:
                continue
            if name in ("swarm_default",):
                continue
            score = sum(1 for t in triggers if t in msg_lower)
            if score > best_score:
                best_score = score
                best_name = name
                best_template = tpl
                _pkg.logger.debug("Template %s score=%d", name, score)

        return best_name, best_template

    def _extract_specifics(self, message: str) -> dict:
        """
        Extract specifics from the message to customize subtasks.

        Detects:
          - Stack/language (Rust, Go, Python, etc.)
          - Framework (axum, django, actix, etc.)
          - Domain (trading, web, mobile, etc.)
          - Context hints

        Returns:
            Dict with 'stack', 'framework', 'domain', 'context'.
        """
        msg_lower = message.lower()
        specifics: dict = {
            "stack": "",
            "framework": "",
            "domain": "",
            "context": "",
        }

        # Stack detection
        stacks = {
            "rust": "Rust",
            "go": "Go",
            "golang": "Go",
            "python": "Python",
            "typescript": "TypeScript",
            "javascript": "JavaScript",
            "react": "React",
            "svelte": "Svelte",
            "vue": "Vue.js",
        }
        for keyword, name in stacks.items():
            if keyword in msg_lower:
                specifics["stack"] = name
                break

        # Framework detection
        frameworks = {
            "axum": "Axum",
            "actix": "Actix-web",
            "django": "Django",
            "flask": "Flask",
            "fastapi": "FastAPI",
            "spring": "Spring Boot",
            "next": "Next.js",
            "express": "Express.js",
            "gin": "Gin",
        }
        for keyword, name in frameworks.items():
            if keyword in msg_lower:
                specifics["framework"] = name
                break

        # Domain detection
        domains = {
            "trading": "trading cuantitativo",
            "web": "web",
            "api": "API",
            "mobile": "móvil",
            "cli": "CLI",
            "database": "base de datos",
            "ml": "machine learning",
            "ai": "inteligencia artificial",
            "blockchain": "blockchain",
            "security": "seguridad",
        }
        for keyword, name in domains.items():
            if keyword in msg_lower:
                specifics["domain"] = name
                break

        # Build context string
        parts = []
        if specifics["stack"]:
            parts.append(f"Stack: {specifics['stack']}")
        if specifics["framework"]:
            parts.append(f"Framework: {specifics['framework']}")
        if specifics["domain"]:
            parts.append(f"Dominio: {specifics['domain']}")
        specifics["context"] = ". ".join(parts) if parts else ""

        return specifics

    def _customize_description(self, description: str, specifics: dict) -> str:
        """Inject specifics into a subtask description."""
        if specifics["stack"] and "stack" in description.lower():
            return description
        if specifics["stack"]:
            description = description.replace(
                "usar el stack especificado",
                f"usar {specifics['stack']}"
            )
        return description
