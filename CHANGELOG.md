# CHANGELOG — AGENTIC Multi-Agent Harness

> Documento de trazabilidad de cambios. Todas las implementaciones, mejoras y correcciones aplicadas al sistema multi-agente.

---

## [2026-07-05] Auditoría 5 Proyectos + CHANGELOG

### Mejoras
- Creación de CHANGELOG.md como documento de trazabilidad oficial
- Auditoría completa de estructura .opencode/ y harness/ en los 5 proyectos:
  - Verificación de archivos nuevos: task_planner.py, session_context.py, task_orchestrator.py
  - Verificación de tests: test_task_planner.py, test_session_context.py, test_orchestrator.py
  - Verificación de configuración preservada: project_config.yaml, routing_rules.yaml, token_budgets.yaml
  - Verificación de importaciones y funcionamiento en todos los proyectos
- Investigación web sobre patrones de orquestación multi-agente 2026:
  - DAG, event-driven, y actor model como patrones dominantes
  - Difficulty-aware dynamic routing
  - Self-optimising workflows (AgentConductor, AFlow)
  - Self-healing agent pipelines con 3 modos de fallo
- Identificación de 10 falencias documentadas en AUDIT_REPORT.md

### Archivos
- `CHANGELOG.md` (este archivo)
- `AUDIT_REPORT.md` — Hallazgos, web research, brainstorm y plan de mejora

---

## [2026-07-03] fix: Corrección de dependencias en DAG + limpieza dead dirs

### Correcciones
- Bug en cálculo de dep_ids en TaskPlanner: usaba fórmula incorrecta
- Ahora usa mapping directo idx_to_id (template index → subtask ID)
- API template ahora produce 2 niveles: 1 builder + 3 guardian en paralelo
  - Antes producía 4 niveles secuenciales por el bug de dependencias
- Eliminados 18 directorios muertos de skills antiguas en AGENTIC
- Deploy script (deploy_v2.py) ahora limpia automáticamente dead dirs

### Tests
- 76/76 tests pasando (32 existentes + 44 nuevos)
- 0 warnings de dependencia circular

### Archivos modificados
- `harness/orchestrator/task_planner.py` — Fix dep_ids con idx_to_id mapping
- `harness/tests/test_task_planner.py` — Test actualizado para nuevo DAG (2 niveles)
- `C:\Users\USUARIO\AppData\Local\Temp\opencode\deploy_v2.py` — Clean dead dirs automático

---

## [2026-07-03] feat: Plan-and-Execute con DAG parallelism y SessionContext

### Nuevos módulos

#### `harness/orchestrator/task_planner.py` (489 líneas)
- Descompone peticiones del usuario en DAG de subtareas atómicas
- 11 templates de plan: implement_api, implement_feature, fix_bug, research, refactor, security_audit, deploy, docs, test, database, general
- Auto-detección por keywords + scoring
- DAG con niveles: paralelo (sin dependencias) + secuencial (con dependencias)
- Inyección de stack/lenguaje, framework, dominio desde el mensaje
- `SubTask` dataclass: id, agent, description, dependencies, expected_output, context_hint
- `TaskPlan` con métodos: get_levels(), get_pending(), get_next_level(), mark_completed(), is_complete(), get_summary()

#### `harness/orchestrator/session_context.py`
- Preserva estado de sesión entre iteraciones
- Persistencia a LanceDB (opcional, fallback a in-memory)
- Tracking de subtareas completadas y sus resultados
- Soporte multi-sesión
- `SessionState` dataclass con plan, messages, completed flag
- `SessionContext` con get_or_create(), mark_subtask_done(), add_message(), get_status()

#### `harness/orchestrator/task_orchestrator.py`
- Orquesta plan + ejecución + comunicación entre agentes
- `process_message()`: planifica y prepara contexto estructurado
- `process_completion()`: avanza al siguiente nivel del DAG
- `get_summary()`: estado human-readable de la sesión
- Comunicación entre agentes via AgentBus
- Broadcast de plan a todos los agentes involucrados
- `OrchestratorResult` dataclass con todo el contexto de ejecución

### Modificaciones

#### `harness/orchestrator/agent_dispatcher.py`
- `dispatch_async()` ahora acepta `plan_context` opcional
- Incluye `execution_plan` en el resultado del dispatch
- `reasoning_mode = "guided_by_plan"` cuando hay plan

#### `harness/orchestrator/delegation_engine.py`
- Nuevos métodos: `plan_task()`, `route_with_plan()`, `get_plan_summary()`

#### `harness/run.py`
- Flujo principal usa `TaskOrchestrator` en lugar de routing simple
- Muestra plan de ejecución al usuario (niveles, paralelo/secuencial)
- Muestra subtareas completadas y progreso
- Inyecta `plan_context` en dispatch
- Output final con estado de sesión y próximos pasos

### Tests
- 44 nuevos tests (76 total):
  - `test_task_planner.py`: 26 tests (todos los templates, DAG, dependencias, dataclasses)
  - `test_session_context.py`: 10 tests (creación, persistencia, completitud, mensajes)
  - `test_orchestrator.py`: 16 tests (flujo completo, agentes objetivo, serialización)

---

## [2026-07-02] feat: Async default + embedding centralizado + Hermes path

### Mejoras
- **Async por defecto**: dispatch_async() con asyncio.gather() es ahora el DEFAULT
  - Eliminado flag `--async` (innecesario)
  - Eliminado código muerto de parsing async_mode
- **Embedding centralizado**: `harness/memory_rag/embeddings.py` como ÚNICA fuente
  - Reemplaza `_make_embedding` duplicado en 4+ módulos
- **.env.example actualizado**: `HERMES_ROOT` con ruta default a Hermes_Memory_Proyects

### Archivos
- `harness/memory_rag/embeddings.py` — Nueva función centralizada make_embedding()
- `.env.example` — Documentación de HERMES_ROOT para memoria compartida

---

## [2026-06-??] Token Optimization Sprint

### Mejoras (5 métodos, parallel-preserving)
- Output Token Control (max_tokens por agente, 512 default vs 4096)
- Skill Pre-compilation (.md → .min.md, 53% avg savings, 19 skills)
- Semantic Caching (LanceDB, hash exacto + búsqueda vectorial, TTL)
- Smart RAG Adaptive-k (selección dinámica de chunks 2-15, 35-50% menos)
- Context Compaction (sliding window + summary)

---

## [2026-06-??] Purge: 18 Agentes → 8 Universales

### Cambio estructural
- Eliminados 18 agentes especializados → 8 roles universales:
  - coordinator, builder, scientist, guardian, evolve, evolve-researcher, evolve-engineer, evolve-analyzer
- Eliminados 18 skills antiguos → 6 skills actuales:
  - evolve, quant-trading, alpha-research, risk-execution, hedgefund, auto
- ~3461 líneas de código muerto eliminadas
- Aliases antiguos (@swe, @pm, @qa) mapean a roles universales

---

## [2026-06-??] Hermes Bridge + Evolve Loop

### Nuevos módulos
- Hermes Bridge: sincronización bidireccional AGENTIC ↔ Hermes_Memory_Proyects
- Trajectory Compressor: compresión de conversaciones (45% savings)
- FTS5 Search: búsqueda full-text con SQLite FTS5
- Nudge System: persistencia automática de contexto valioso
- Agent Builder: construcción de agentes desde patrones de cognición
- Agent Pruner: eliminación de agentes auto-generados no utilizados

---

## [2026-06-??] Tests + CI/CD + Benchmarks

### Infraestructura de calidad
- 32 tests iniciales (7 suites, 8 fixtures)
- CI/CD Pipeline: 4 GitHub workflows (ci.yml, security-scan, dependabot, codecov)
- Benchmark Suite: 5 benchmarks (routing 94.4%, memory 5.5K ops/s, cache 100%, compression 64.4%)
- Plugin System: ToolRegistry con auto-discovery via importlib
- Security audit: 0 issues (reemplazados 4 `__import__()`)
- Trading skills con CQE Rust: quant-trading, alpha-research, risk-execution

---

## [2026-06-??] Fundación inicial

### Setup
- Despliegue base a 5 proyectos (Aeternus, CQE, HC, Onyx, PDV)
- 8 agentes universales con auto-detección SIN @
- Async Agent Dispatcher con asyncio.gather
- LanceDB memory con 9+ colecciones
- ModelRouter (local/cloud híbrido)
- HITLGuard (Human-in-the-Loop)
- SandboxLoop para ejecución autónoma
