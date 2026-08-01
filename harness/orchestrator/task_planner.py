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
from dataclasses import dataclass, field
from typing import ClassVar

from harness.memory_rag.compaction import structured_compact

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
    dependencies: list[str] = field(default_factory=list)
    expected_output: str = ""
    context_hint: str = ""
    completed: bool = False
    result: str = ""
    confidence_impact: str = "neutral"  # "critical" | "neutral" | "validation"
    estimated_latency_ms: float | None = None  # Peso para ruta crítica (LAMaS, ADR-0034)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "description": self.description,
            "dependencies": list(self.dependencies),
            "expected_output": self.expected_output,
            "context_hint": self.context_hint,
            "completed": self.completed,
            "result": self.result,
            "confidence_impact": self.confidence_impact,
        }


@dataclass
class TaskPlan:
    """A complete execution plan with DAG structure."""
    session_id: str
    original_message: str
    subtasks: list[SubTask] = field(default_factory=list)
    template_name: str = ""  # Which template was used to create this plan

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "original_message": self.original_message,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "template_name": self.template_name,
        }

    def get_levels(self) -> list[list[SubTask]]:
        """
        Group subtasks into execution levels (topological sort).

        Level 0: no dependencies (run in PARALLEL)
        Level 1: depend on level 0
        Level 2: depend on level 1
        etc.

        LAMaS-lite (ADR-0034): dentro de cada nivel, las subtasks de la ruta
        crítica se ordenan primero para reducir el tiempo end-to-end sin
        violar dependencias.
        """
        remaining = {s.id: s for s in self.subtasks}
        completed_ids: set = set()
        levels: list[list[SubTask]] = []

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
            levels.append(self._order_level(level))
            for s in level:
                del remaining[s.id]
                completed_ids.add(s.id)

        return levels

    def _order_level(self, level: list[SubTask]) -> list[SubTask]:
        """Ordena un nivel priorizando la ruta crítica (LAMaS-lite, ADR-0034).

        Args:
            level: subtasks listas para ejecutarse en este nivel.

        Returns:
            Subtasks ordenadas: las críticas primero, el resto en orden.
        """
        if len(level) <= 1:
            return level
        try:
            from harness.orchestrator.latency_aware import CriticalPath
            return CriticalPath().optimize(level)
        except ImportError:
            # Fallback: mantener orden original si no se puede importar.
            return level

    def get_pending(self) -> list[SubTask]:
        """Get subtasks that are not yet completed and whose deps are met."""
        completed_ids = {s.id for s in self.subtasks if s.completed}
        return [
            s for s in self.subtasks
            if not s.completed
            and all(dep in completed_ids for dep in s.dependencies)
        ]

    def get_next_level(self) -> list[SubTask]:
        """Get the next level of subtasks ready for execution."""
        pending = self.get_pending()
        if not pending:
            return []
        # Group by dependency depth
        {s.id for s in self.subtasks if s.completed}
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

    def get_current_level_num(self) -> int:
        """Get the 0-based index of the current execution level.

        Recorre los niveles devueltos por get_levels() y retorna el indice
        del primer nivel que contiene subtareas sin completar.
        Si todos los niveles estan completos, retorna la cantidad de niveles
        (equivalente a "nivel finalizado").
        """
        completed_ids = {s.id for s in self.subtasks if s.completed}
        for idx, level in enumerate(self.get_levels()):
            if any(s.id not in completed_ids for s in level):
                return idx
        return len(self.get_levels())

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

SUBTASK_TEMPLATES: dict[str, dict] = {
    # ==========================================================================
    # SWISS WATCH: MAXIMA VELOCIDAD, CERO COLISIONES.
    # Nivel 0: builder+guardian+scientist en PARALELO.
    # - Builder escribe CODIGO (src/)
    # - Guardian escribe PLAN de tests (texto, 0 archivos)
    # - Scientist INVESTIGA (texto, 0 archivos)
    # Nivel 1: guardian escribe TESTS sobre codigo ya existente (tests/)
    # => VELOCIDAD de paralelo + 0 colisiones (nadie toca el mismo archivo)
    # ==========================================================================
    "swarm_default": {
        "triggers": ["implement", "create", "build", "develop", "haz", "crea", "implementa", "construye", "construir", "hacer", "realiza", "desarrolla", "genera", "produce", "prepara", "disena"],
        "description": "CUADRILLA: 6 agentes paralelos + bugfix dedicado",
        "subtasks": [
            {"agent": "coordinator", "description": "PLAN: dividir trabajo en modulos (core, api, db) + tests + docs", "deps": [], "expected_output": "Plan de trabajo dividido en modulos", "context_hint": "Coordinator: produces SOLO un plan. Cada builder trabajara en su modulo SIN colision.", "confidence_impact": "critical"},
            {"agent": "builder", "description": "CORE: implementar logica de negocio en src/core/ segun plan", "deps": [0], "expected_output": "Modulo core en src/core/", "context_hint": "Builder-core: src/core/. Otros builders: src/api/ y src/db/. Directorios DIFERENTES.", "confidence_impact": "critical"},
            {"agent": "builder", "description": "API: implementar endpoints y routing en src/api/ segun plan", "deps": [0], "expected_output": "Modulo API en src/api/", "context_hint": "Builder-api: src/api/. Builder-core: src/core/. Directorios DIFERENTES.", "confidence_impact": "critical"},
            {"agent": "builder", "description": "DB: implementar modelos y migraciones en src/db/ segun plan", "deps": [0], "expected_output": "Modulo DB en src/db/", "context_hint": "Builder-db: src/db/. Los otros builders: src/core/ y src/api/. CERO colision.", "confidence_impact": "critical"},
            {"agent": "scientist", "description": "INVESTIGAR: mejores practicas y alternativas (solo texto, 0 archivos)", "deps": [], "expected_output": "Recomendaciones tecnicas (solo texto)", "context_hint": "Scientist: produces texto. NO tocas NINGUN archivo de codigo.", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "TESTS: escribir tests unitarios en tests/ para los 3 modulos", "deps": [0], "expected_output": "Tests en tests/ cubriendo core+api+db", "context_hint": "Guardian-tests: trabajas SOLO en tests/. Los builders ya terminaron src/. Directorios DIFERENTES.", "confidence_impact": "validation"},
            {"agent": "guardian", "description": "DOCS: documentar API, modulos y ejemplos de uso", "deps": [0], "expected_output": "Docs en ES-UTF8", "context_hint": "Guardian-docs: escribes documentacion. 0 archivos de codigo fuente.", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "BUGFIX: ejecutar tests, identificar fallos y corregirlos en src/", "deps": [1, 2, 3, 5], "expected_output": "Tests verdes, bugs corregidos", "context_hint": "Guardian-bugfix: EJECUTAS los tests. Si fallan, corriges SOLO el error especifico. No reescribes modulos enteros.", "confidence_impact": "validation"},
            {"agent": "coordinator", "description": "CONSOLIDAR: integrar todos los modulos, tests y documentacion", "deps": [1, 2, 3, 4, 5, 6, 7], "expected_output": "Entrega unificada sin conflictos", "context_hint": "Cada builder en su directorio (core/api/db). Guardian en tests/. Todo separado, 0 conflictos.", "confidence_impact": "critical"},
        ],
    },
    "implement_api": {
        "triggers": ["api", "endpoint", "rest", "graphql", "grpc"],
        "description": "Implementar API",
        "subtasks": [
            {"agent": "builder", "description": "CODIGO: implementar API en src/", "deps": [], "expected_output": "API en src/", "context_hint": "Builder: src/. Guardian: tests/ y texto. CERO colision.", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "PLAN (texto): disenar tests y seguridad para la API", "deps": [], "expected_output": "Plan de testing (texto, 0 archivos)", "context_hint": "Guardian: SOLO texto ahora. Tests los escribiras en tests/ cuando builder termine.", "confidence_impact": "validation"},
            {"agent": "guardian", "description": "TESTS: escribir tests unitarios e integracion en tests/", "deps": [0], "expected_output": "Tests en tests/", "context_hint": "Builder ya termino src/. Tu trabajas en tests/. Archivos DIFERENTES.", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "DOCS + SEGURIDAD: documentar y revisar seguridad", "deps": [0], "expected_output": "Docs + reporte seguridad", "context_hint": "Solo agregas archivos en tests/ y docs/", "confidence_impact": "validation"},
        ],
    },
    "fix_bug": {
        "triggers": ["bug", "fix", "error", "issue", "problema", "bugfix", "hotfix"],
        "description": "Corregir bug: diagnostico + fix + test paralelo",
        "subtasks": [
            {"agent": "scientist", "description": "DIAGNOSTICO: causa raiz del bug (solo texto)", "deps": [], "expected_output": "Diagnostico (texto)", "context_hint": "Scientist: produces texto. Builder corrige.", "confidence_impact": "critical"},
            {"agent": "builder", "description": "FIX: corregir bug en src/ segun diagnostico", "deps": [0], "expected_output": "Bug corregido en src/", "context_hint": "Builder: solo src/. Guardian hara tests en tests/.", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "TEST REGRESION: escribir test en tests/ que prevenga regreso", "deps": [1], "expected_output": "Test regresion en tests/", "context_hint": "Guardian: tests/ solo. Builder ya termino src/.", "confidence_impact": "validation"},
            {"agent": "guardian", "description": "VERIFICAR: ejecutar suite completa", "deps": [1], "expected_output": "Tests verdes", "context_hint": "Suite completa", "confidence_impact": "validation"},
        ],
    },
    "research": {
        "triggers": ["research", "investigar", "study", "analyze", "analysis", "paper", "survey"],
        "description": "Investigacion con prototipo",
        "subtasks": [
            {"agent": "scientist", "description": "RECOPILAR fuentes y analizar (solo texto)", "deps": [], "expected_output": "Fuentes + analisis (texto)", "context_hint": "Scientist: texto. Builder prototipa.", "confidence_impact": "critical"},
            {"agent": "scientist", "description": "SINTETIZAR: conclusiones y recomendaciones (texto)", "deps": [0], "expected_output": "Conclusiones (texto)", "context_hint": "Scientist: texto.", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "DOCUMENTAR: escribir documento de investigacion", "deps": [0], "expected_output": "Documento investigacion", "context_hint": "Solo texto, 0 archivos de codigo", "confidence_impact": "neutral"},
        ],
    },
    "refactor": {
        "triggers": ["refactor", "refactoring", "reestructurar", "clean", "cleanup", "deuda tecnica"],
        "description": "Refactorizar: analisis + refactor + test paralelo",
        "subtasks": [
            {"agent": "scientist", "description": "ANALISIS: puntos de mejora en el codigo (solo texto)", "deps": [], "expected_output": "Analisis (texto)", "context_hint": "Scientist: texto. Builder refactoriza src/.", "confidence_impact": "critical"},
            {"agent": "builder", "description": "REFACTOR: ejecutar refactor en src/ preservando comportamiento", "deps": [0], "expected_output": "Codigo refactorizado en src/", "context_hint": "Builder: src/. Guardian tests en tests/.", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "VERIFICAR: tests post-refactor en tests/", "deps": [1], "expected_output": "Tests 100% en tests/", "context_hint": "Guardian: tests/. Builder ya termino src/.", "confidence_impact": "validation"},
            {"agent": "guardian", "description": "DOCUMENTAR cambios", "deps": [1], "expected_output": "Docs actualizadas", "context_hint": "Actualizar docs", "confidence_impact": "neutral"},
        ],
    },
    "security_audit": {
        "triggers": ["security", "seguridad", "audit", "auditar", "vulnerabilidad", "hardening", "owasp"],
        "description": "Auditoria seguridad",
        "subtasks": [
            {"agent": "guardian", "description": "AUDITAR: vulnerabilidades en codigo (texto + tests/ si aplica)", "deps": [], "expected_output": "Reporte vulnerabilidades + tests en tests/", "context_hint": "Guardian: reporte texto + tests en tests/. Builder corrige src/. CERO colision.", "confidence_impact": "critical"},
            {"agent": "builder", "description": "CORREGIR: vulnerabilidades en src/", "deps": [0], "expected_output": "Codigo corregido en src/", "context_hint": "Builder: src/ solamente.", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Verificar correcciones y escanear nuevamente", "deps": [1], "expected_output": "Verificación de correcciones", "context_hint": "re-ejecutar análisis, confirmar cierre", "confidence_impact": "validation"},
            {"agent": "guardian", "description": "Documentar hallazgos y medidas tomadas", "deps": [1], "expected_output": "Reporte de seguridad final", "context_hint": "incluir CVEs, mitigaciones, recomendaciones", "confidence_impact": "neutral"},
        ],
    },
    "deploy": {
        "triggers": ["deploy", "desplegar", "release", "lanzar", "producción", "production", "ci/cd"],
        "description": "Despliegue",
        "subtasks": [
            {"agent": "builder", "description": "Preparar artefactos de build y release", "deps": [], "expected_output": "Artefactos listos para deploy", "context_hint": "compilar, empaquetar, versionar", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "Ejecutar tests pre-deploy y validaciones", "deps": [0], "expected_output": "Tests pasando, validaciones ok", "context_hint": "tests de integración, smoke tests", "confidence_impact": "validation"},
            {"agent": "builder", "description": "Ejecutar despliegue en el entorno objetivo", "deps": [1], "expected_output": "Deploy completado", "context_hint": "seguir runbook, migraciones si aplica", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Verificar deploy y monitorear estabilidad", "deps": [2], "expected_output": "Verificación post-deploy", "context_hint": "health checks, logs, métricas", "confidence_impact": "validation"},
        ],
    },
    "docs": {
        "triggers": ["document", "documentar", "docs", "readme", "wiki", "manual"],
        "description": "Documentación",
        "subtasks": [
            {"agent": "scientist", "description": "Analizar el código o funcionalidad a documentar", "deps": [], "expected_output": "Entendimiento completo del tema", "context_hint": "revisar código, tests, issues relacionados", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Escribir documentación clara y completa", "deps": [0], "expected_output": "Documentación escrita", "context_hint": "incluir ejemplos, casos de uso, API reference", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "Revisar y corregir documentación", "deps": [1], "expected_output": "Documentación revisada y aprobada", "context_hint": "ortografía, claridad, completitud", "confidence_impact": "validation"},
        ],
    },
    "test": {
        "triggers": ["test", "testing", "coverage", "cobertura", "pruebas"],
        "description": "Testing",
        "subtasks": [
            {"agent": "scientist", "description": "Analizar código para identificar qué testear", "deps": [], "expected_output": "Plan de testing", "context_hint": "caminos críticos, casos borde, integraciones", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Escribir tests unitarios", "deps": [0], "expected_output": "Tests unitarios implementados", "context_hint": "usar framework del proyecto, cobertura >80%", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "Escribir tests de integración", "deps": [1], "expected_output": "Tests de integración implementados", "context_hint": "probar interacción entre componentes", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "Ejecutar suite completa y reportar resultados", "deps": [2], "expected_output": "Reporte de tests", "context_hint": "documentar pasados, fallidos, cobertura", "confidence_impact": "validation"},
        ],
    },
    "database": {
        "triggers": ["database", "db", "sql", "query", "migración", "schema", "modelo de datos"],
        "description": "Trabajo con base de datos",
        "subtasks": [
            {"agent": "scientist", "description": "Diseñar o analizar el esquema de datos", "deps": [], "expected_output": "Esquema diseñado", "context_hint": "normalización, índices, relaciones", "confidence_impact": "critical"},
            {"agent": "builder", "description": "Implementar migraciones y modelos", "deps": [0], "expected_output": "Migraciones + modelos implementados", "context_hint": "usar ORM/herramienta del proyecto", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Escribir tests de integración con BD", "deps": [1], "expected_output": "Tests de BD implementados", "context_hint": "testear consultas, transacciones, rollbacks", "confidence_impact": "validation"},
            {"agent": "guardian", "description": "Documentar esquema y consultas importantes", "deps": [1], "expected_output": "Documentación de BD", "context_hint": "diagrama ER, consultas frecuentes", "confidence_impact": "neutral"},
        ],
    },
    "debate": {
        "triggers": ["debate", "discutir", "consenso", "votar", "criticar", "revisar"],
        "description": "Debate multi-agente con consolidación",
        "subtasks": [
            {"agent": "coordinator", "description": "Facilitar debate entre agentes sobre la decisión", "deps": [], "expected_output": "Debate facilitado y turnos gestionados", "context_hint": "coordinar perspectivas de builder, scientist y guardian", "confidence_impact": "critical"},
            {"agent": "builder", "description": "Presentar perspectiva de implementación técnica", "deps": [0], "expected_output": "Perspectiva de implementación", "context_hint": "stack, arquitectura, rendimiento, viabilidad técnica", "confidence_impact": "neutral"},
            {"agent": "scientist", "description": "Presentar perspectiva de investigación y análisis", "deps": [0], "expected_output": "Perspectiva de investigación", "context_hint": "alternativas, literatura, datos, evidencia", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "Presentar perspectiva de calidad y riesgo", "deps": [0], "expected_output": "Perspectiva de calidad/riesgo", "context_hint": "tests, seguridad, mantenibilidad, riesgos", "confidence_impact": "neutral"},
            {"agent": "coordinator", "description": "Consolidar perspectivas en decisión final", "deps": [1, 2, 3], "expected_output": "Decisión final consolidada", "context_hint": "integrar las tres perspectivas en una recomendación", "confidence_impact": "critical"},
        ],
    },
    "general": {
        "triggers": [],
        "description": "Tarea general multi-agente paralelo",
        "subtasks": [
            {"agent": "builder", "description": "CODIGO: implementar en src/", "deps": [], "expected_output": "Implementacion src/", "context_hint": "Builder: src/. Guardian: tests/. CERO colision.", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "PLAN (texto): disenar tests y seguridad", "deps": [], "expected_output": "Plan calidad (texto)", "context_hint": "Guardian: SOLO texto ahora. Tests en tests/ luego.", "confidence_impact": "validation"},
            {"agent": "scientist", "description": "INVESTIGAR: mejores practicas (solo texto)", "deps": [], "expected_output": "Recomendaciones (texto)", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "TESTS + DOCS: escribir tests en tests/ y docs", "deps": [0], "expected_output": "Tests + docs", "context_hint": "Guardian: tests/ solamente. Builder src/ ya termino.", "confidence_impact": "validation"},
            {"agent": "coordinator", "description": "Consolidar resultados", "deps": [0, 1, 2, 3], "expected_output": "Entrega unificada", "confidence_impact": "critical"},
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

        logger.info(
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
                logger.debug("Specific template %s selected (score=%d)", name, score)
                return name, tpl

        # Fase 2: Si no hay template especifico -> SWARM DINAMICO (escala segun alcance)
        # Cualquier mensaje con al menos 1 keyword de implementacion activa el escalado
        swarm_triggers = SUBTASK_TEMPLATES["swarm_default"].get("triggers", [])
        swarm_score = sum(1 for t in swarm_triggers if t in msg_lower)
        if swarm_score >= 1:  # Solo 1 keyword y va a dinamico
            logger.debug("SWARM DINAMICO (score=%d)", swarm_score)
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
                logger.debug("Template %s score=%d", name, score)

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

