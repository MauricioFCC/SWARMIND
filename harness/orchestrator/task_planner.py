"""
Task Planner — Decomposes user requests into a DAG of atomic subtasks.

Given a user message like "implementa una API REST con Rust, tests y docs",
the planner produces a structured plan:

  Level 0 (parallel): [builder: implementar API, scientist: investigar patrones]
  Level 1 (sequential, depends on L0): [guardian: tests, guardian: docs]

Each subtask specifies:
  - agent: who executes it (builder, scientist, guardian, evolve)
  - description: what to do
  - dependencies: list of subtask IDs that must complete first
  - expected_output: what the agent must produce
  - context_hint: additional guidance

The coordinator uses this plan to dispatch work in the correct order,
parallelizing where possible and sequencing where there are dependencies.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SubTask:
    """A single atomic subtask in the execution plan."""
    id: str
    agent: str          # builder | scientist | guardian | evolve | coordinator
    description: str
    dependencies: List[str] = field(default_factory=list)
    expected_output: str = ""
    context_hint: str = ""
    completed: bool = False
    result: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "description": self.description,
            "dependencies": list(self.dependencies),
            "expected_output": self.expected_output,
            "context_hint": self.context_hint,
            "completed": self.completed,
            "result": self.result,
        }


@dataclass
class TaskPlan:
    """A complete execution plan with DAG structure."""
    session_id: str
    original_message: str
    subtasks: List[SubTask] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "original_message": self.original_message,
            "subtasks": [s.to_dict() for s in self.subtasks],
        }

    def get_levels(self) -> List[List[SubTask]]:
        """
        Group subtasks into execution levels (topological sort).

        Level 0: no dependencies (run in PARALLEL)
        Level 1: depend on level 0
        Level 2: depend on level 1
        etc.
        """
        remaining = {s.id: s for s in self.subtasks}
        completed_ids: set = set()
        levels: List[List[SubTask]] = []

        while remaining:
            level = [
                s for s in remaining.values()
                if all(dep in completed_ids for dep in s.dependencies)
            ]
            if not level:
                # Circular dependency — break it by adding all remaining
                level = list(remaining.values())
                logger.warning(
                    "Circular dependency detected in plan %s. "
                    "Breaking by adding %d remaining subtasks.",
                    self.session_id, len(level),
                )
            levels.append(level)
            for s in level:
                del remaining[s.id]
                completed_ids.add(s.id)

        return levels

    def get_pending(self) -> List[SubTask]:
        """Get subtasks that are not yet completed and whose deps are met."""
        completed_ids = {s.id for s in self.subtasks if s.completed}
        return [
            s for s in self.subtasks
            if not s.completed
            and all(dep in completed_ids for dep in s.dependencies)
        ]

    def get_next_level(self) -> List[SubTask]:
        """Get the next level of subtasks ready for execution."""
        pending = self.get_pending()
        if not pending:
            return []
        # Group by dependency depth
        completed_ids = {s.id for s in self.subtasks if s.completed}
        # The ones with the shallowest dependency depth
        min_deps = min(len(s.dependencies) for s in pending)
        return [s for s in pending if len(s.dependencies) == min_deps]

    def mark_completed(self, subtask_id: str, result: str = "") -> None:
        """Mark a subtask as completed with its result."""
        for s in self.subtasks:
            if s.id == subtask_id:
                s.completed = True
                s.result = result
                logger.info(
                    "Subtask %s (%s) completed. %d/%d done.",
                    subtask_id, s.agent,
                    sum(1 for x in self.subtasks if x.completed),
                    len(self.subtasks),
                )
                return
        logger.warning("Subtask %s not found in plan %s.", subtask_id, self.session_id)

    def is_complete(self) -> bool:
        """Check if all subtasks are complete."""
        return all(s.completed for s in self.subtasks)

    def get_summary(self) -> str:
        """Human-readable summary of plan status."""
        total = len(self.subtasks)
        done = sum(1 for s in self.subtasks if s.completed)
        lines = [
            f"📋 Plan ({done}/{total} subtasks completadas):",
        ]
        for level_idx, level in enumerate(self.get_levels()):
            is_parallel = len(level) > 1
            mode = "⚡ PARALELO" if is_parallel else "→ SECUENCIAL"
            lines.append(f"\n  Nivel {level_idx} ({mode}):")
            for s in level:
                status = "✅" if s.completed else "⏳" if s in self.get_pending() else "⏸️"
                deps_str = f" [deps: {', '.join(s.dependencies)}]" if s.dependencies else ""
                lines.append(f"    {status} [{s.agent}] {s.description}{deps_str}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Task decomposition templates
# ---------------------------------------------------------------------------

# Each template defines subtasks for a common task type.
# - agent: who should execute
# - description: what to do
# - deps: indices of subtasks this depends on (0-based within template)
# - expected_output: what the agent must produce

SUBTASK_TEMPLATES: Dict[str, Dict] = {
    "implement_api": {
        "triggers": ["api", "endpoint", "rest", "graphql", "grpc"],
        "description": "Implementación de API",
        "subtasks": [
            {"agent": "builder", "description": "Diseñar e implementar la API con endpoints, validación y errores", "deps": [], "expected_output": "Código de la API funcionando", "context_hint": "usar el stack especificado (Rust/Go/Python)"},
            {"agent": "guardian", "description": "Escribir tests unitarios y de integración para la API", "deps": [0], "expected_output": "Tests que cubren todos los endpoints", "context_hint": "cobertura >80%, casos borde incluidos"},
            {"agent": "guardian", "description": "Documentar la API con ejemplos de uso", "deps": [0], "expected_output": "Documentación de la API", "context_hint": "ejemplos curl, request/response, códigos de error"},
            {"agent": "guardian", "description": "Revisar seguridad de la API (autenticación, validación, rate limiting)", "deps": [0], "expected_output": "Reporte de seguridad", "context_hint": "OWASP Top 10, inyección, autenticación"},
        ],
    },
    "implement_feature": {
        "triggers": ["implement", "feature", "funcionalidad", "create", "build", "develop"],
        "description": "Implementación de funcionalidad",
        "subtasks": [
            {"agent": "scientist", "description": "Analizar requisitos y diseñar la solución", "deps": [], "expected_output": "Diseño de la solución", "context_hint": "considerar arquitectura actual, patrones existentes"},
            {"agent": "builder", "description": "Implementar la funcionalidad", "deps": [0], "expected_output": "Código implementado", "context_hint": "seguir el diseño acordado, código limpio"},
            {"agent": "guardian", "description": "Escribir tests para la nueva funcionalidad", "deps": [1], "expected_output": "Tests unitarios y de integración", "context_hint": "probar casos normales, borde y error"},
            {"agent": "guardian", "description": "Documentar la funcionalidad y actualizar changelog", "deps": [1], "expected_output": "Documentación actualizada", "context_hint": "README, API docs, ejemplos"},
        ],
    },
    "fix_bug": {
        "triggers": ["bug", "fix", "error", "issue", "problema", "bugfix", "hotfix"],
        "description": "Corrección de bug",
        "subtasks": [
            {"agent": "scientist", "description": "Diagnosticar la causa raíz del bug", "deps": [], "expected_output": "Diagnóstico con causa raíz identificada", "context_hint": "revisar logs, stack traces, reproducción"},
            {"agent": "builder", "description": "Implementar la corrección", "deps": [0], "expected_output": "Código corregido", "context_hint": "mínimo cambio necesario, no romper otras funcionalidades"},
            {"agent": "guardian", "description": "Escribir test que prevenga regresión", "deps": [1], "expected_output": "Test de regresión", "context_hint": "el test debe fallar sin la corrección"},
            {"agent": "guardian", "description": "Verificar que todos los tests existentes sigan pasando", "deps": [1], "expected_output": "Tests verdes", "context_hint": "ejecutar suite completa"},
        ],
    },
    "research": {
        "triggers": ["research", "investigar", "study", "analyze", "analysis", "paper", "survey"],
        "description": "Investigación",
        "subtasks": [
            {"agent": "scientist", "description": "Recopilar información y fuentes relevantes", "deps": [], "expected_output": "Fuentes recopiladas y organizadas", "context_hint": "buscar papers, documentación, ejemplos"},
            {"agent": "scientist", "description": "Analizar y sintetizar hallazgos", "deps": [0], "expected_output": "Análisis estructurado con conclusiones", "context_hint": "comparar enfoques, ventajas/desventajas"},
            {"agent": "builder", "description": "Crear prototipo o PoC si aplica", "deps": [1], "expected_output": "Prototipo funcional o PoC", "context_hint": "implementar solo lo mínimo para validar"},
            {"agent": "guardian", "description": "Documentar hallazgos y recomendaciones", "deps": [1], "expected_output": "Documento de investigación completo", "context_hint": "incluir referencias, metodología, conclusiones"},
        ],
    },
    "refactor": {
        "triggers": ["refactor", "refactoring", "reestructurar", "clean", "cleanup", "deuda técnica"],
        "description": "Refactorización",
        "subtasks": [
            {"agent": "scientist", "description": "Analizar código actual e identificar puntos de mejora", "deps": [], "expected_output": "Análisis con áreas de mejora identificadas", "context_hint": "buscar duplicación, complejidad, acoplamiento"},
            {"agent": "builder", "description": "Ejecutar refactorización preservando comportamiento", "deps": [0], "expected_output": "Código refactorizado", "context_hint": "cambios incrementales, mantener API pública"},
            {"agent": "guardian", "description": "Ejecutar tests para verificar que nada se rompió", "deps": [1], "expected_output": "Tests pasando al 100%", "context_hint": "ejecutar suite completa, comparar antes/después"},
            {"agent": "guardian", "description": "Documentar cambios y actualizar referencias", "deps": [1], "expected_output": "Documentación actualizada", "context_hint": "actualizar docs que referencien código cambiado"},
        ],
    },
    "security_audit": {
        "triggers": ["security", "seguridad", "audit", "auditar", "vulnerabilidad", "hardening", "owasp"],
        "description": "Auditoría de seguridad",
        "subtasks": [
            {"agent": "guardian", "description": "Auditar código en busca de vulnerabilidades", "deps": [], "expected_output": "Reporte de vulnerabilidades encontradas", "context_hint": "OWASP Top 10, inyección SQL, XSS, CSRF"},
            {"agent": "builder", "description": "Corregir vulnerabilidades encontradas", "deps": [0], "expected_output": "Código corregido", "context_hint": "priorizar por severidad, mínimo cambio"},
            {"agent": "guardian", "description": "Verificar correcciones y escanear nuevamente", "deps": [1], "expected_output": "Verificación de correcciones", "context_hint": "re-ejecutar análisis, confirmar cierre"},
            {"agent": "guardian", "description": "Documentar hallazgos y medidas tomadas", "deps": [1], "expected_output": "Reporte de seguridad final", "context_hint": "incluir CVEs, mitigaciones, recomendaciones"},
        ],
    },
    "deploy": {
        "triggers": ["deploy", "desplegar", "release", "lanzar", "producción", "production", "ci/cd"],
        "description": "Despliegue",
        "subtasks": [
            {"agent": "builder", "description": "Preparar artefactos de build y release", "deps": [], "expected_output": "Artefactos listos para deploy", "context_hint": "compilar, empaquetar, versionar"},
            {"agent": "guardian", "description": "Ejecutar tests pre-deploy y validaciones", "deps": [0], "expected_output": "Tests pasando, validaciones ok", "context_hint": "tests de integración, smoke tests"},
            {"agent": "builder", "description": "Ejecutar despliegue en el entorno objetivo", "deps": [1], "expected_output": "Deploy completado", "context_hint": "seguir runbook, migraciones si aplica"},
            {"agent": "guardian", "description": "Verificar deploy y monitorear estabilidad", "deps": [2], "expected_output": "Verificación post-deploy", "context_hint": "health checks, logs, métricas"},
        ],
    },
    "docs": {
        "triggers": ["document", "documentar", "docs", "readme", "wiki", "manual"],
        "description": "Documentación",
        "subtasks": [
            {"agent": "scientist", "description": "Analizar el código o funcionalidad a documentar", "deps": [], "expected_output": "Entendimiento completo del tema", "context_hint": "revisar código, tests, issues relacionados"},
            {"agent": "guardian", "description": "Escribir documentación clara y completa", "deps": [0], "expected_output": "Documentación escrita", "context_hint": "incluir ejemplos, casos de uso, API reference"},
            {"agent": "guardian", "description": "Revisar y corregir documentación", "deps": [1], "expected_output": "Documentación revisada y aprobada", "context_hint": "ortografía, claridad, completitud"},
        ],
    },
    "test": {
        "triggers": ["test", "testing", "coverage", "cobertura", "pruebas"],
        "description": "Testing",
        "subtasks": [
            {"agent": "scientist", "description": "Analizar código para identificar qué testear", "deps": [], "expected_output": "Plan de testing", "context_hint": "caminos críticos, casos borde, integraciones"},
            {"agent": "guardian", "description": "Escribir tests unitarios", "deps": [0], "expected_output": "Tests unitarios implementados", "context_hint": "usar framework del proyecto, cobertura >80%"},
            {"agent": "guardian", "description": "Escribir tests de integración", "deps": [1], "expected_output": "Tests de integración implementados", "context_hint": "probar interacción entre componentes"},
            {"agent": "guardian", "description": "Ejecutar suite completa y reportar resultados", "deps": [2], "expected_output": "Reporte de tests", "context_hint": "documentar pasados, fallidos, cobertura"},
        ],
    },
    "database": {
        "triggers": ["database", "db", "sql", "query", "migración", "schema", "modelo de datos"],
        "description": "Trabajo con base de datos",
        "subtasks": [
            {"agent": "scientist", "description": "Diseñar o analizar el esquema de datos", "deps": [], "expected_output": "Esquema diseñado", "context_hint": "normalización, índices, relaciones"},
            {"agent": "builder", "description": "Implementar migraciones y modelos", "deps": [0], "expected_output": "Migraciones + modelos implementados", "context_hint": "usar ORM/herramienta del proyecto"},
            {"agent": "guardian", "description": "Escribir tests de integración con BD", "deps": [1], "expected_output": "Tests de BD implementados", "context_hint": "testear consultas, transacciones, rollbacks"},
            {"agent": "guardian", "description": "Documentar esquema y consultas importantes", "deps": [1], "expected_output": "Documentación de BD", "context_hint": "diagrama ER, consultas frecuentes"},
        ],
    },
    "general": {
        "triggers": [],
        "description": "Tarea general",
        "subtasks": [
            {"agent": "scientist", "description": "Analizar la solicitud y planificar enfoque", "deps": [], "expected_output": "Plan de acción", "context_hint": "entender requisitos, identificar riesgos"},
            {"agent": "builder", "description": "Ejecutar la implementación principal", "deps": [0], "expected_output": "Implementación completada", "context_hint": "seguir mejores prácticas del stack"},
            {"agent": "guardian", "description": "Verificar calidad: tests, seguridad, documentación", "deps": [1], "expected_output": "Verificación de calidad completada", "context_hint": "tests pasando, sin vulnerabilidades, documentado"},
        ],
    },
}


# ---------------------------------------------------------------------------
# TaskPlanner
# ---------------------------------------------------------------------------

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

    def __init__(self) -> None:
        self._counter: int = 0

    def decompose(self, message: str) -> TaskPlan:
        """
        Decompose a user message into a structured TaskPlan.

        Strategy:
          1. Detect task type from keywords and patterns
          2. Load matching template
          3. Customize subtasks based on specifics in message
          4. Assign a session ID

        Args:
            message: The user's request/message.

        Returns:
            A TaskPlan with subtasks organized for DAG execution.
        """
        import uuid
        msg_lower = message.lower()

        # --- 1. Detect template ---
        template = self._detect_template(msg_lower)

        # --- 2. Extract specifics from message ---
        specifics = self._extract_specifics(message)

        # --- 3. Build subtasks from template ---
        subtasks: List[SubTask] = []
        for idx, tpl in enumerate(template["subtasks"]):
            self._counter += 1
            subtask_id = f"st-{self._counter}"
            dep_ids = [f"st-{self._counter - (len(tpl['deps']) - dep_idx)}"
                       for dep_idx in tpl["deps"]]

            description = self._customize_description(
                tpl["description"], specifics
            )

            subtasks.append(SubTask(
                id=subtask_id,
                agent=tpl["agent"],
                description=description,
                dependencies=dep_ids,
                expected_output=tpl["expected_output"],
                context_hint=specifics.get("context", tpl["context_hint"]),
            ))

        plan = TaskPlan(
            session_id=str(uuid.uuid4())[:8],
            original_message=message,
            subtasks=subtasks,
        )

        logger.info(
            "Plan %s: %s — %d subtasks en %d niveles",
            plan.session_id, template["description"],
            len(plan.subtasks), len(plan.get_levels()),
        )

        return plan

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _detect_template(self, msg_lower: str) -> Dict:
        """
        Detect the best matching template for a message.

        Scores templates by number of matching trigger keywords.
        Falls back to 'general' template.
        """
        best_score = 0
        best_template = SUBTASK_TEMPLATES["general"]

        for name, tpl in SUBTASK_TEMPLATES.items():
            triggers = tpl.get("triggers", [])
            if not triggers:
                continue
            score = sum(1 for t in triggers if t in msg_lower)
            if score > best_score:
                best_score = score
                best_template = tpl
                logger.debug("Template %s score=%d", name, score)

        return best_template

    def _extract_specifics(self, message: str) -> Dict:
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
        specifics: Dict = {
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

    def _customize_description(self, description: str, specifics: Dict) -> str:
        """Inject specifics into a subtask description."""
        if specifics["stack"] and "stack" in description.lower():
            return description
        if specifics["stack"]:
            description = description.replace(
                "usar el stack especificado",
                f"usar {specifics['stack']}"
            )
        return description
