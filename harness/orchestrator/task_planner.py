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
    confidence_impact: str = "neutral"  # "critical" | "neutral" | "validation"

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
            "confidence_impact": self.confidence_impact,
        }


@dataclass
class TaskPlan:
    """A complete execution plan with DAG structure."""
    session_id: str
    original_message: str
    subtasks: List[SubTask] = field(default_factory=list)
    template_name: str = ""  # Which template was used to create this plan

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "original_message": self.original_message,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "template_name": self.template_name,
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

SUBTASK_TEMPLATES: Dict[str, Dict] = {
    # ==========================================================================
    # TEMPLATES COORDINADOS: paralelo SEGURO con pre-plan.
    # Estrategia: 
    #   1. Builder crea PLAN rapido (nivel 0) listando archivos a modificar
    #   2. TODOS los agentes trabajan en PARALELO sabiendo quien hace que
    #   3. Nadie toca el mismo archivo porque conocen los boundaries
    # ==========================================================================
    "implement": {
        "triggers": ["implement", "create", "build", "develop", "haz", "crea", "implementa"],
        "description": "Implementacion paralela coordinada",
        "subtasks": [
            {"agent": "builder", "description": "PLAN RAPIDO: listar archivos a crear/modificar (max 3 lineas)", "deps": [], "expected_output": "Lista de archivos que editara cada agente", "context_hint": "Builder: produce SOLO un plan. Ej: 'src/api.rs: implementar endpoints, tests/api_test.rs: tests'", "confidence_impact": "critical"},
            {"agent": "builder", "description": "IMPLEMENTAR segun plan: solo los archivos que anunciaste", "deps": [0], "expected_output": "Codigo implementado", "context_hint": "Builder: editas SOLO los archivos que listaste en el plan. Guardian trabajara en tests/.", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "TESTS en archivos SEPARADOS (tests/) segun el plan del builder", "deps": [0], "expected_output": "Tests >80% cobertura", "context_hint": "Guardian: creas tests en tests/ NUNCA tocas archivos del builder. Usa el plan para saber que testear.", "confidence_impact": "validation"},
            {"agent": "scientist", "description": "INVESTIGAR alternativas (solo texto, 0 archivos de codigo)", "deps": [], "expected_output": "Recomendaciones tecnicas", "context_hint": "Scientist: produces texto. No tocas NINGUN archivo del proyecto.", "confidence_impact": "critical"},
            {"agent": "coordinator", "description": "Consolidar resultados de todos los agentes", "deps": [1, 2, 3], "expected_output": "Entrega unificada", "context_hint": "Coordinator: builder y guardian trabajaron en archivos DIFERENTES. No hay conflictos.", "confidence_impact": "critical"},
        ],
    },
    "implement_api": {
        "triggers": ["api", "endpoint", "rest", "graphql", "grpc"],
        "description": "Implementar API",
        "subtasks": [
            {"agent": "builder", "description": "Implementar API con endpoints y validacion", "deps": [], "expected_output": "API funcionando", "context_hint": "Stack especificado (Rust/Go/Python)", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Tests unitarios e integracion para API", "deps": [0], "expected_output": "Tests pasando", "context_hint": "Cobertura >80%, casos borde", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "Documentar API con ejemplos", "deps": [0], "expected_output": "Documentacion API", "context_hint": "Curl, request/response, errores", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "Revisar seguridad de la API", "deps": [0], "expected_output": "Reporte seguridad", "context_hint": "OWASP, auth, rate limiting", "confidence_impact": "validation"},
        ],
    },
    "implement_feature": {
        "triggers": ["implement", "feature", "funcionalidad", "create", "build", "develop"],
        "description": "Implementar funcionalidad",
        "subtasks": [
            {"agent": "scientist", "description": "Analizar requisitos y disenar solucion (solo texto, no editar archivos)", "deps": [], "expected_output": "Diseno solucion", "context_hint": "Scientist: produces diseno. Builder implementara.", "confidence_impact": "critical"},
            {"agent": "builder", "description": "Implementar funcionalidad segun diseno", "deps": [0], "expected_output": "Codigo implementado", "context_hint": "Builder: implementas el diseno del scientist", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Tests para nueva funcionalidad", "deps": [1], "expected_output": "Tests unitarios + integracion", "context_hint": "Casos normal, borde, error", "confidence_impact": "validation"},
            {"agent": "guardian", "description": "Documentar funcionalidad y actualizar changelog", "deps": [1], "expected_output": "Docs actualizadas", "context_hint": "README, API docs, ejemplos", "confidence_impact": "neutral"},
        ],
    },
    "fix_bug": {
        "triggers": ["bug", "fix", "error", "issue", "problema", "bugfix", "hotfix"],
        "description": "Corregir bug",
        "subtasks": [
            {"agent": "scientist", "description": "Diagnosticar causa raiz del bug (solo texto, no codigo)", "deps": [], "expected_output": "Diagnostico con causa raiz", "context_hint": "Logs, stack traces, reproduccion", "confidence_impact": "critical"},
            {"agent": "builder", "description": "Implementar correccion segun diagnostico", "deps": [0], "expected_output": "Codigo corregido", "context_hint": "Builder: solo tu editas archivos. Minimo cambio necesario.", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Test que prevenga regresion", "deps": [1], "expected_output": "Test regresion", "context_hint": "Debe fallar sin la correccion", "confidence_impact": "validation"},
            {"agent": "guardian", "description": "Verificar tests existentes", "deps": [1], "expected_output": "Tests verdes", "context_hint": "Suite completa", "confidence_impact": "validation"},
        ],
    },
    "research": {
        "triggers": ["research", "investigar", "study", "analyze", "analysis", "paper", "survey"],
        "description": "Investigacion",
        "subtasks": [
            {"agent": "scientist", "description": "Recopilar fuentes relevantes (solo texto, no editar codigo)", "deps": [], "expected_output": "Fuentes organizadas", "context_hint": "Scientist: solo produces texto", "confidence_impact": "critical"},
            {"agent": "scientist", "description": "Analizar y sintetizar hallazgos", "deps": [0], "expected_output": "Analisis con conclusiones", "context_hint": "Comparar enfoques, pros/cons", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Documentar hallazgos y recomendaciones", "deps": [0], "expected_output": "Documento investigacion", "context_hint": "Referencias, metodologia, conclusiones", "confidence_impact": "neutral"},
        ],
    },
    "refactor": {
        "triggers": ["refactor", "refactoring", "reestructurar", "clean", "cleanup", "deuda tecnica"],
        "description": "Refactorizar",
        "subtasks": [
            {"agent": "scientist", "description": "Analizar codigo y puntos de mejora (solo texto)", "deps": [], "expected_output": "Areas de mejora", "context_hint": "Scientist: solo produce analisis. Builder refactoriza.", "confidence_impact": "critical"},
            {"agent": "builder", "description": "Ejecutar refactor preservando comportamiento", "deps": [0], "expected_output": "Codigo refactorizado", "context_hint": "Builder: solo tu editas archivos. Cambios incrementales.", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Verificar tests post-refactor", "deps": [1], "expected_output": "Tests 100% verdes", "context_hint": "Comparar antes/despues", "confidence_impact": "validation"},
            {"agent": "guardian", "description": "Documentar cambios y referencias", "deps": [1], "expected_output": "Docs actualizadas", "context_hint": "Actualizar docs que referencien codigo cambiado", "confidence_impact": "neutral"},
        ],
    },
    "security_audit": {
        "triggers": ["security", "seguridad", "audit", "auditar", "vulnerabilidad", "hardening", "owasp"],
        "description": "Auditoria seguridad",
        "subtasks": [
            {"agent": "guardian", "description": "Auditar vulnerabilidades en codigo", "deps": [], "expected_output": "Reporte vulnerabilidades", "context_hint": "OWASP Top 10, SQLi, XSS, CSRF", "confidence_impact": "critical"},
            {"agent": "builder", "description": "Corregir vulnerabilidades encontradas", "deps": [0], "expected_output": "Codigo corregido", "context_hint": "Builder: solo tu editas archivos. Priorizar por severidad.", "confidence_impact": "critical"},
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
    "deploy": {
        "triggers": ["deploy", "desplegar", "release", "lanzar", "produccion", "production", "ci/cd"],
        "description": "Despliegue",
        "subtasks": [
            {"agent": "builder", "description": "Preparar artefactos build y release", "deps": [], "expected_output": "Artefactos listos", "context_hint": "Builder: solo tu preparas artefactos", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "Tests pre-deploy y validaciones", "deps": [0], "expected_output": "Validaciones ok", "context_hint": "Guardian: builder ya termino, no modifiques sus archivos", "confidence_impact": "validation"},
            {"agent": "builder", "description": "Ejecutar despliegue en entorno objetivo", "deps": [1], "expected_output": "Deploy completado", "context_hint": "Seguir runbook, migraciones", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Verificar deploy y monitorear estabilidad", "deps": [2], "expected_output": "Verificacion post-deploy", "context_hint": "Health checks, logs, metricas", "confidence_impact": "validation"},
        ],
    },
    "docs": {
        "triggers": ["document", "documentar", "docs", "readme", "wiki", "manual"],
        "description": "Documentacion",
        "subtasks": [
            {"agent": "scientist", "description": "Analizar funcionalidad a documentar (solo texto)", "deps": [], "expected_output": "Entendimiento del tema", "context_hint": "Scientist: solo produces texto, no editas codigo", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Escribir documentacion clara", "deps": [0], "expected_output": "Docs escritas", "context_hint": "Ejemplos, casos de uso, API reference", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "Revisar y corregir documentacion", "deps": [1], "expected_output": "Docs revisadas", "context_hint": "Ortografia, claridad, completitud", "confidence_impact": "validation"},
        ],
    },
    "test": {
        "triggers": ["test", "testing", "coverage", "cobertura", "pruebas"],
        "description": "Testing",
        "subtasks": [
            {"agent": "scientist", "description": "Analizar codigo y planificar tests (solo texto)", "deps": [], "expected_output": "Plan testing", "context_hint": "Scientist: solo produces plan. Guardian escribe tests.", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Escribir tests unitarios", "deps": [0], "expected_output": "Tests unitarios", "context_hint": "Framework del proyecto, cobertura >80%", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "Escribir tests de integracion", "deps": [1], "expected_output": "Tests integracion", "context_hint": "Interaccion entre componentes", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "Ejecutar suite completa y reportar", "deps": [2], "expected_output": "Reporte tests", "context_hint": "Pasados, fallidos, cobertura", "confidence_impact": "validation"},
        ],
    },
    "database": {
        "triggers": ["database", "db", "sql", "query", "migracion", "schema", "modelo datos"],
        "description": "Base de datos",
        "subtasks": [
            {"agent": "scientist", "description": "Disenar esquema de datos (solo texto)", "deps": [], "expected_output": "Esquema disenado", "context_hint": "Scientist: produces diseno. Builder implementa.", "confidence_impact": "critical"},
            {"agent": "builder", "description": "Implementar migraciones y modelos segun diseno", "deps": [0], "expected_output": "Migraciones + modelos", "context_hint": "Builder: solo tu editas archivos", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Tests de integracion con BD", "deps": [1], "expected_output": "Tests BD", "context_hint": "Consultas, transacciones, rollbacks", "confidence_impact": "validation"},
            {"agent": "guardian", "description": "Documentar esquema y consultas", "deps": [1], "expected_output": "Docs BD", "context_hint": "Diagrama ER, consultas frecuentes", "confidence_impact": "neutral"},
        ],
    },
    "debate": {
        "triggers": ["debate", "discutir", "consenso", "votar", "criticar", "revisar"],
        "description": "Debate multi-agente (solo texto, nadie edita archivos)",
        "subtasks": [
            {"agent": "coordinator", "description": "Facilitar debate entre agentes", "deps": [], "expected_output": "Debate facilitado", "context_hint": "Solo texto, nadie edita archivos de codigo", "confidence_impact": "critical"},
            {"agent": "builder", "description": "Perspectiva de implementacion tecnica", "deps": [0], "expected_output": "Perspectiva tecnica", "context_hint": "Stack, arquitectura, rendimiento", "confidence_impact": "neutral"},
            {"agent": "scientist", "description": "Perspectiva de investigacion y analisis", "deps": [0], "expected_output": "Perspectiva investigacion", "context_hint": "Alternativas, literatura, datos", "confidence_impact": "neutral"},
            {"agent": "guardian", "description": "Perspectiva de calidad y riesgo", "deps": [0], "expected_output": "Perspectiva calidad/riesgo", "context_hint": "Tests, seguridad, mantenibilidad", "confidence_impact": "neutral"},
            {"agent": "coordinator", "description": "Consolidar perspectivas en decision final", "deps": [1, 2, 3], "expected_output": "Decision final", "context_hint": "Integrar las 3 perspectivas", "confidence_impact": "critical"},
        ],
    },
    "general": {
        "triggers": [],
        "description": "Tarea general paralela coordinada",
        "subtasks": [
            {"agent": "builder", "description": "PLAN + IMPLEMENTAR: primero listar archivos, luego implementar", "deps": [], "expected_output": "Codigo implementado", "context_hint": "Builder: anuncias los archivos que crearas. Nadie mas los tocara.", "confidence_impact": "critical"},
            {"agent": "scientist", "description": "Investigar dominio (solo texto, 0 archivos de codigo)", "deps": [], "expected_output": "Recomendaciones", "context_hint": "Scientist: produces texto. No tocas archivos.", "confidence_impact": "critical"},
            {"agent": "guardian", "description": "Tests + docs en archivos SEPARADOS (tests/)", "deps": [0], "expected_output": "Calidad verificada", "context_hint": "Guardian: trabajas en tests/. No tocas archivos del builder.", "confidence_impact": "validation"},
            {"agent": "coordinator", "description": "Consolidar resultados", "deps": [0, 1, 2], "expected_output": "Entrega unificada", "context_hint": "Sin conflictos: cada agente trabajo en archivos diferentes", "confidence_impact": "critical"},
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
        self._injector = None  # Lazy import

    def _get_injector(self):
        """Lazy import de ContextInjector para evitar circular imports."""
        if self._injector is None:
            from harness.memory_rag.context_injector import ContextInjector
            self._injector = ContextInjector(always_inject=True)
        return self._injector

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
        template_name, template = self._detect_template(msg_lower)

        # --- 2. Extract specifics from message ---
        specifics = self._extract_specifics(message)

        # --- 3. Build subtasks from template ---
        # Map: template index → counter-based subtask ID
        # deps use template indices (0-based), converted to counter-based IDs
        subtasks: List[SubTask] = []
        idx_to_id: Dict[int, str] = {}
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
            # para evitar que el LLM los olvide durante sesiones largas
            injector = self._get_injector()
            injected_desc = injector.inject(description, agent_role=tpl["agent"])

            subtasks.append(SubTask(
                id=subtask_id,
                agent=tpl["agent"],
                description=injected_desc,
                dependencies=dep_ids,
                expected_output=tpl["expected_output"],
                context_hint=specifics.get("context", tpl["context_hint"]),
                confidence_impact=tpl.get("confidence_impact", "neutral"),
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

        # Fase 1: Buscar template especifico (implement_api, fix_bug, research, etc.)
        # Si hay coincidencia EXACTA con triggers de un template especifico, usarlo
        for name, tpl in SUBTASK_TEMPLATES.items():
            triggers = tpl.get("triggers", [])
            # Saltar templates genericos (implement, general) en Fase 1
            if not triggers or name in ("implement", "general"):
                continue
            score = sum(1 for t in triggers if t in msg_lower)
            if score >= 2:  # Dos o mas keywords = template especifico
                logger.debug("Specific template %s selected (score=%d)", name, score)
                return name, tpl

        # Fase 2: Si no hay template especifico, detectar si es implementacion generica
        impl_triggers = SUBTASK_TEMPLATES["implement"].get("triggers", [])
        impl_score = sum(1 for t in impl_triggers if t in msg_lower)
        if impl_score >= 2:
            logger.debug("Implement template selected (score=%d)", impl_score)
            return "implement", SUBTASK_TEMPLATES["implement"]

        for name, tpl in SUBTASK_TEMPLATES.items():
            triggers = tpl.get("triggers", [])
            if not triggers:
                continue
            if name in ("implement",):
                continue
            score = sum(1 for t in triggers if t in msg_lower)
            if score > best_score:
                best_score = score
                best_name = name
                best_template = tpl
                logger.debug("Template %s score=%d", name, score)

        return best_name, best_template

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

