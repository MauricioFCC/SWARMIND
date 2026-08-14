"""Plantillas de descomposición de tareas — ``SUBTASK_TEMPLATES``.

Extracción mecánica desde ``harness/orchestrator/task_planner.py``
(sin cambios de lógica).

Cada template define subtasks para un tipo de tarea común:
- ``agent``: quién la ejecuta (builder, scientist, guardian, coordinator).
- ``description``: qué hacer.
- ``deps``: índices de subtasks de las que depende (0-based dentro del template).
- ``expected_output``: qué debe producir el agente.
"""

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
