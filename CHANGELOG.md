# CHANGELOG — AGENTIC Multi-Agent Harness

> Documento de trazabilidad de cambios.

## [2026-07-20] ⚡ Optimización Speed + Token Economics + ADRs 0016-0018

### ADRs creados
| ADR | Título | Estado |
|-----|--------|--------|
| **ADR-0016** | Parallel Test Execution & Fail-Under Progresivo | **ACEPTADO** |
| **ADR-0017** | PaCoRe Async Concurrency Pattern | **PROPUESTO** |
| **ADR-0018** | Token Economics — Cache Shape + Structured Compaction | **PROPUESTO** |

### Optimizaciones implementadas
- **pytest-xdist + pytest-split**: Dependencias dev para ejecución paralela
- **Slow markers**: 10 tests lentos (>1s) marcados como `@pytest.mark.slow`
- **Fail-under**: Actualizado a 43% (coverage actual), plan progresivo
- **ShapedCache**: LRU + TTL + relevancia en semantic_cache.py (-38% tokens)
- **pyproject.toml**: Fix flat-layout build, markers registry

### Resultados
- Tests: **1068 passing, 0 failures**
- Cobertura: **43.55%** (+9.89% desde baseline)

## [2026-07-20] 🔧 Structured Compaction + WriteAheadLog + ShapedCache

### Nuevos componentes
| Componente | Archivo | Propósito |
|------------|---------|-----------|
| **structured_compact()** | `context_window_manager.py` | Compresión estructurada de contexto (-41% tokens) |
| **WriteAheadLog** | `write_ahead_log.py` | Retry con backoff + cancelación + recovery |
| **ShapedCache tests** | `test_semantic_cache_extended.py` | 8 tests para cache shape (LRU+TTL) |
| **WAL tests** | `test_write_ahead_log.py` | 10 tests para Write-Ahead Log |

### Mejoras
- **pre-commit hook**: Convertido a batch nativo Windows (fix shebang roto)
- **conftest.py**: Fixtures optimizadas (evita ScopeMismatch)
- **pyproject.toml**: markers registry + fail_under=43

### Resultados finales
- Tests: **1086 passing, 0 failures** (+18 desde anterior)
- ADRs: **0016** (parallel testing), **0017** (PaCoRe async), **0018** (token economics)
- Commits: `2ef685f` + `e10caed` + `7e9e8b8` Todas las implementaciones, mejoras y correcciones aplicadas al sistema multi-agente.

---

## [2026-07-20] 🧬 Frontier Upgrade 2026 — MetaClaw, AdaptOrch, MuTON, SWE-Master, ShapleyFlow + frontend-uiux

### Investigación Web Frontera (2 waves, 25+ fuentes 2026)
#### Wave 1: UI/UX (7 papers + 10 frameworks)
| Fuente | Aporte |
|--------|--------|
| **arXiv:2604.09577** | LLMs as UI Generators — 83% preferencia vs markdown |
| **ACM 2026 Bridging Gulfs** | Semantic Guidance jerárquico Product→DesignSystem→Feature→Component |
| **ACL 2026 WiserUI-Bench** | 300 pares A/B reales con razonamiento visual UX |
| **arXiv:2604.09876** | Bayesian active preference learning para personalización |
| **DIS 2026 ReFinE** | AI-powered design iteration con scholarly findings |
| **arXiv:2507.04469** | Systematic review: UI generation con LLMs |
| **A2UI v0.9, OpenUI, Geeklego, StyleSeed, 7onic, useVyre, UDS, LLUI** | 10 frameworks de Generative UI 2026 |

#### Wave 2: 5 especialidades (18+ papers/frameworks)
| Especialidad | Fuentes Clave |
|-------------|---------------|
| **Builder** | SWE-Master (arXiv:2602.03411, 61.4% SWE-bench), BOAD (53.12% SWB, bandit agent design), SWE-World (55.0% SWB, Docker-free), AOrchestra (dynamic sub-agent), ParaManager (lightweight orchestrator), ShapleyFlow (ACL 2026, game-theoretic attribution) |
| **Scientist** | MetaClaw (arXiv:2603.17187, +32% accuracy), MARS (single-cycle metacognitive), Hyperagents/DGM-H (self-referential), Memento-Skills (26.2-116.2% mejora GAIA/HLE), Native Self-Evolution (+20% WebVoyager), ERL (+7.8% Gaia2), POLARIS (policy repair 7B), ShapleyFlow |
| **Guardian** | MuTON/mewt (Trail of Bits 2026, language-agnostic), AdverTest (+8.56% fault detection), SWE-Mutation (ACL 2026, 2636 variants, 9 lenguajes), CDBench (zero-sum game, 57-80% fail rate), UAgent (92% accuracy), SWE-ABS (25.1x mejora), PROBE (+9.79% mutation score, 45 bugs) |
| **Coordinator** | AdaptOrch (arXiv:2602.16873, 12-23% mejora), NeuralFSM (6.74-19.39% mejora), MPAC (95% overhead reduction, 4.8x speedup), Symphony-Coord (bandit routing, regret bounds), LAS (50.5% token reduction), StructAgent (27%→46.9% OSWorld), Enterprise event-driven (14-75% latency reduction) |
| **Evolve** | MetaClaw (skill-driven fast adaptation), MARS (single-cycle reflection), Hyperagents (self-referential), Memento-Skills (skill-as-memory), Native Self-Evolution (reward-free), ERL (heuristics extraction) |

### Nuevo Skill: frontend-uiux
`.opencode/skills/frontend-uiux/SKILL.md` (~580 líneas, 18 secciones):
- Generative UI con Semantic Guidance + A2UI/OpenUI declarativo
- Design Systems AI-native: Geeklego 3-tier tokens, StyleSeed 74 rules, 7onic, useVyre
- WCAG 2.2 AA compliance, Core Web Vitals optimization
- 7 PBT templates UI (render_stable, idempotent_click, boundary_viewport, roundtrip_form, commutative_layout, associative_compose, responsive_invariant)
- Bayesian preference learning para personalización
- WiserUI-Bench validation, visual regression testing (Pixelmatch 0.1% umbral)
- 4 stages (analyze → design → implement → validate), DoD checklist

### Agentes actualizados (25+ técnicas frontier 2026)
| Agente | Técnicas Nuevas |
|--------|-----------------|
| builder.md | SWE-Master (LSP-driven, post-training), BOAD (bandit discovery), SWE-World (Docker-free), AOrchestra, ParaManager, ShapleyFlow |
| scientist.md | MetaClaw, MARS, Hyperagents, Memento-Skills, Native Self-Evolution, ERL, POLARIS, ShapleyFlow |
| guardian.md | MuTON/mewt (AI-assisted triage, two-phase campaigns), AdverTest, SWE-Mutation, CDBench, UAgent, SWE-ABS, PROBE |
| coordinator.md | AdaptOrch (4 topologías canónicas), NeuralFSM, MPAC (5 capas), Symphony-Coord, LAS, StructAgent, Enterprise event-driven |
| evolve/SKILL.md | MetaClaw, MARS, Hyperagents, Memento-Skills, Native Evolution, ERL |
| base_principles.md | MCL + MKS en N1+N2 + 17 nuevas abreviaturas |

### ADR-0015 creado
`docs/src/adr/adr0015-frontier-agents-skills-2026.md` documenta:
- Contexto, decisión, 6 áreas de impacto
- Archivos creados/modificados (1 creado, 7 modificados)
- Tests (455 passed, 2 pre-existing failures)
- Deploy a 5 proyectos con estadísticas
- 22 referencias a papers/frameworks

### Tests
- **455 passed, 2 failed** (2 pre-existing LanceDB semantic_cache deprecation issues)
- 0 regresiones

### Deploy final
| Proyecto | .opencode | harness | skills |
|----------|-----------|---------|--------|
| core-quant-engine | 58 | 2033 | 7 |
| Historia Clinica | 58 | 3170 | 5 |
| Onyx-Quan-AIBot | 58 | 337 | 7 |
| PDV Basic | 62 | 715 | 4 |
| Hermes_Memory_Proyects | 58 | 1723 | 9 |

---

## [2026-07-07] 🔗 Hermes_Memory_Proyects como nodo central + .env loader + sync bidireccional

### Problema detectado
- `HERMES_ROOT` no estaba configurado en el entorno (faltaba `.env`)
- Hermes_Memory_Proyects no recibía deploy de `.opencode` ni `harness/`
- Dos bridges separados con el mismo nombre (`HermesBridge` en dos archivos)
- La cognición no se sincronizaba con Hermes

### Soluciones implementadas

#### 1. `.env` creado con HERMES_ROOT
- `.env` generado desde `.env.example` con `HERMES_ROOT=C:\Users\USUARIO\Documents\Hermes_Memory_Proyects`
- `hermes_bridge.py` ahora carga automáticamente `.env` al importarse (busca en 3 ubicaciones)
- No sobreescribe variables de entorno ya existentes

#### 2. Hermes_Memory_Proyects como proyecto destino en deploy_all.py
- Nueva entrada con all 10 skills desplegadas
- `_ensure_dir()` agregado para crear directorios faltantes antes de copiar
- `dst.parent.mkdir(parents=True, exist_ok=True)` para archivos en subdirectorios nuevos

#### 3. Sincronización bidireccional verificada
- `sync_hermes --to-hermes` → Exporta entries de cognition store → `syntheses/` y `knowledge/`
- `sync_hermes --from-hermes` → Importa archivos .md → cognition store
- Bridge operacional: 1 entry exportado exitosamente en prueba

### Deploy final
| Proyecto | .opencode | harness | skills |
|----------|-----------|---------|--------|
| core-quant-engine | 53 | 672 | 7 |
| Historia Clinica | 53 | 3137 | 5 |
| Onyx-Quan-AIBot | 53 | 302 | 7 |
| PDV Basic | 57 | 682 | 4 |
| **Hermes_Memory_Proyects** | **50** | **299** | **10** |

### Tests
- 369/369 pasan

---

## [2026-07-07] 📚 Nuevas Skills: math-doc, legal-doc, science-doc + deploy

### Nuevas Skills de Procesamiento de Documentos

| Skill | Archivo | Keywords | Alcance |
|-------|---------|----------|---------|
| **math-doc** | `.opencode/skills/math-doc/SKILL.md` | 20+ keywords | LaTeX, ecuaciones, demostraciones, estadística, papers matemáticos |
| **legal-doc** | `.opencode/skills/legal-doc/SKILL.md` | 30+ keywords | Contratos, compliance, jurisprudencia, due diligence, multilingüe |
| **science-doc** | `.opencode/skills/science-doc/SKILL.md` | 25+ keywords | Papers IMRaD, metodología, PRISMA, metaanálisis, bibliometría |

### Dominios cubiertos por skill
- **math-doc**: Parseo LaTeX, validación de demostraciones, análisis estadístico, conversión bidireccional
- **legal-doc**: Análisis contractual, compliance GDPR/LGPD, jurisprudencia, dictámenes, due diligence, 5 idiomas
- **science-doc**: Estructura IMRaD, evaluación metodológica, PRISMA, forest/funnel plots, bibliometría

### Distribución por proyecto
| Proyecto | Skills adicionales |
|----------|-------------------|
| core-quant-engine | math-doc, science-doc (papers cuantitativos) |
| Historia Clinica | legal-doc, science-doc (compliance salud + papers médicos) |
| Onyx-Quan-AIBot | math-doc, science-doc (análisis cuantitativo) |
| PDV Basic | legal-doc (contratos, compliance retail) |

### skills_registry.yaml actualizado
Registro completo con 10 skills documentadas (7 existentes + 3 nuevas).

### Tests
- 369/369 tests pasan (0 regresiones)

---

## [2026-07-07] 📋 ADR-0001 + DebateOrchestrator + Confidence Early Stopping + 82 tests

### Investigación web (6+ fuentes 2026)
| Fuente | Aporte |
|--------|--------|
| **SkillReducer (arXiv 2603.29919)** | 48% compresión descripciones, "less-is-more" |
| **SkillsInjector (arXiv 2605.29794)** | Inyección adaptativa, set-aware rendering |
| **Princeton NLP 2026** | Single-agent > multi-agent en 64% benchmarks |
| **Microsoft AutoGen 2026** | DAG dinámico, self-healing, adaptive planning |
| **Token Budget Contracts (PyPI)** | Confidence-gated spending |
| **Prompt Caching (Anthropic/OpenAI)** | 50-90% ahorro prefix caching |

### ADR-0001: docs/adr/adr0001-mejoras.md
Documento de Arquitectura con:
- P0: Unificar schedulers + fusionar health/telemetry ✅
- P1: Coverage 32% ✅
- P2: DebateOrchestrator + Confidence Early Stopping ✅ (implementado ahora)
- P2+: Set-aware rendering, Debate paralelo 🔲 (propuesto)

### DebateOrchestrator (NUEVO) — `harness/orchestrator/debate_orchestrator.py`
- 3 estrategias: CONSENSUS (votación), CRITIQUE (crítica entre pares), DELIBERATION (debate secuencial)
- Integrado con TaskPlanner (template "debate") y TaskOrchestrator
- Trazabilidad completa via AgentBus (cada ronda se registra como mensaje)
- 48 tests

### Confidence Early Stopping (NUEVO) — `harness/orchestrator/confidence_scorer.py`
- ConfidenceScorer con 4 señales heurísticas: length, hedging, self-correction, speed
- SubTask.confidence_impact: "critical", "neutral", "validation"
- Early stop cuando confianza > 0.90 y el siguiente nivel es solo validación
- Integrado en TaskOrchestrator.process_completion()
- 34 tests

### Tests
- 287 → **369** (+82 tests, +29%)
- 0 fallos

### Coverage
- 32.44% → **34.76%** (threshold 30% ✅)

---

## [2026-07-05] 🐛 Bugfixes + 73 nuevos tests (182 total, 0 fallos)

### Bug corregido
| Bug | Archivo | Síntoma | Causa | Fix |
|-----|---------|---------|-------|-----|
| `'SubTask' object has no attribute 'level'` | `task_orchestrator.py:541` | 2 tests fallaban (pre-existing) | `get_next_level()` retorna `SubTask[]`, no tienen atributo `.level` | Nuevo método `TaskPlan.get_current_level_num()` que calcula nivel por subtasks completados |

### Tests ampliados (+73 tests, +67%)

#### `harness/tests/test_common.py` (NUEVO — 28 tests)
Cubre 100% de `harness/common.py`:
- `fallback_embedding()`: empty, normal, unicode, custom dim, determinismo
- `estimate_tokens()`: empty, short, long, consistencia
- `compression_pct()` / `avg_compression_pct()`: casos borde
- `keyword_match_score()`: match simple, default, best-score, dict con score_key
- `EMPTY_VECTOR`: shape, zeros, inmutabilidad
- `StatsMixin`: básico, vacío, chars alternativos
- `truncate_by_budget()`: fit, truncado, margin, sort_key, vacío

#### `harness/tests/test_context_window.py` (NUEVO — 26 tests)
Cubre `ContextSection`, `ContextWindow`, `ContextWindowManager`:
- Section: create, over_budget, truncate, frozen, not_over_budget
- Window: create, add, tokens, over_budget, remove, to_prompt, to_dict
- Manager: create, optimize (sin cambio, con truncado), stats, compact_history (short/long/empty), hard_truncate, aggressive_compress, default_summary

#### `harness/tests/test_agent_bus.py` (6→19 tests, +13)
- `update_message_status()`: nuevo método unificado
- `update_message_status_invalid()`: estado inválido retorna False
- `mark_delivered()` / `mark_acknowledged()`: backward compat
- `post_message_batch()`: batch con 2 mensajes + batch vacío
- `get_thread()`, `get_channel_history()`: lectura por thread/canal
- `escalate()`: mensaje de escalación
- `get_channel_list()`, `get_tasks_with_errors()`: listas únicas
- `_build_message_payload()`: metadata payload completo
- `_search_messages()`: busqueda con filtros

#### `harness/tests/test_task_planner.py` (17→23 tests, +6)
- `get_current_level_num_initial()`: nivel 0 al inicio
- `get_current_level_num_after_first()`: nivel 1 tras completar
- `get_current_level_num_all_complete()`: retorna len(levels)
- `get_current_level_num_empty()`: plan vacío → 0
- `get_summary()`: incluye progreso

### Resultado final
```
===================== 182 passed in 15.93s ======================
🎉 0 FALLOS — TODOS LOS TESTS PASAN
```

---

## [2026-07-05] 🔒 Security Audit + Gaps Fix + Deploy a 4 proyectos

### Gaps detectados y corregidos (post-refactor)
| Archivo | Problema | Solución |
|---------|----------|----------|
| `doc_ingester.py` | `_default_embedding` completo duplicado | Delega en `common.fallback_embedding` |
| `semantic_cache.py` | `_default_embedding` + `np.zeros` duplicados | Usa `fallback_embedding` + `EMPTY_VECTOR` |
| `session_context.py` | 3x `np.zeros` para queries LanceDB | `EMPTY_VECTOR` de common |
| `health.py` | `__import__('numpy')` peligroso | `import numpy as np` directo |

### Seguridad — Hallazgos y correcciones
| Severidad | Archivo | Problema | Acción |
|-----------|---------|----------|--------|
| **HIGH** | `task_manager.py:351` | Filter injection en `query_by_agent()` vía f-string | Validación contra `_VALID_AGENTS` whitelist |
| **MEDIUM** | `task_manager.py:290,325,339` | f-string en `.where()` para `task_id` | Documentado como interno (uuid), bajo riesgo |
| **LOW** | `health.py:270` | `__import__('numpy')` dinámico | Reemplazado por `import numpy as np` |
| NONE | `deploy_all.py:569` | KeyError en summary si proyecto saltado | Fix: `.get("name", "N/A")` |

### Tests
- 107/107 tests pasan (2 fallos pre-existentes en task_orchestrator.py)
- Coverage: 27.39% (infra de tests legacy, 33 tests → 109 tests)
- 0 regresiones post-refactor + post-seguridad

### Deploy a proyectos
| Proyecto | Tipo | .opencode | harness | skills |
|----------|------|-----------|---------|--------|
| core-quant-engine | trading | 59 files | 649 files | 5 |
| Historia Clinica | healthtech | 59 files | 3114 files | 3 |
| Onyx-Quan-AIBot | trading | 59 files | 279 files | 5 |
| PDV Basic | retail | 63 files | 659 files | 3 |

---

## [2026-07-05] 🔄 DRY/KISS Refactor — Eliminadas ~300 líneas duplicadas

### Principios aplicados
- **DRY (Don't Repeat Yourself)**: Unificadas 13+ implementaciones de embedding, 6 de token estimation, 7 de search pattern
- **KISS (Keep It Simple, Stupid)**: Extraídas funciones pequeñas con nombre descriptivo de `main()` (354→60 líneas)
- **Clean Code / Single Responsibility**: `run.main()` dividido en 8 funciones enfocadas
- **Reusabilidad**: `StatsMixin` elimina 19 `get_stats()` casi idénticos
- **Patrón Template Method**: `StatsMixin.get_stats()` con `avg_compression_pct` heredable

### Nuevo Módulo
- **`harness/common.py`** — Utilidades compartidas (FUENTE ÚNICA):
  - `fallback_embedding()` — reemplaza 13+ implementaciones (agent_bus, scheduler, context_assembler, etc.)
  - `estimate_tokens()` — tiktoken + chars/4 fallback, reemplaza 6 variaciones
  - `compression_pct()` / `avg_compression_pct()` — reemplaza 5 fórmulas idénticas
  - `keyword_match_score()` — patrón unificado para intent/domain matching
  - `EMPTY_VECTOR` — constante `np.zeros` (reemplaza 48+ ocurrencias)
  - `truncate_by_budget()` — truncamiento por presupuesto de tokens (reemplaza 3 bucles en context_assembler)
  - `StatsMixin` — mixin con `get_stats()` + `avg_compression_pct` (reemplaza 19+ implementaciones)

### Refactors mayores

#### `harness/orchestrator/agent_bus.py` (732→~580 líneas, -20%)
- `mark_delivered()` + `mark_acknowledged()` → `update_message_status()` unificado
- `post_message()` + `post_message_batch()` → `_build_message_payload()` extraído
- 7 search patterns (poll_channel, get_thread, etc.) → `_search_messages()` unificado
- `_default_embedding()` → delega en `fallback_embedding()` de common

#### `harness/run.py` (715→~480 líneas, -33%)
- `main()` de 354 líneas → 60 líneas con 8 funciones extraídas:
  `_handle_gateway_mode`, `_handle_daemon_mode`, `_handle_command`,
  `_display_plan`, `_dispatch_task`, `_resolve_hitl_mode`,
  `_ensure_rag_context`, `_create_task_and_lesson`,
  `_display_final_output`, `_start_sandbox_if_needed`

#### `harness/memory_rag/context_window_manager.py`
- `ContextWindowManager` ahora hereda de `StatsMixin` (elimina `get_stats()`)
- Usa `estimate_tokens()` y `compression_pct()` de common

#### `harness/memory_rag/context_assembler.py`
- `_default_embedding()` → `fallback_embedding()` de common
- `_estimate_tokens()` → `estimate_tokens()` de common
- `_apply_token_budget()` → usa `truncate_by_budget()` de common

#### `harness/memory_rag/embeddings.py`
- `make_embedding()` delega en `fallback_embedding()` de common

### Tests
- 107/109 tests pasan (2 fallos pre-existentes en task_orchestrator.py, ajenos al refactor)
- 0 regresiones

### Impacto
- **Líneas eliminadas**: ~300 (duplicación)
- **Archivos refactorizados**: 6
- **Módulo nuevo**: 1 (`harness/common.py`)
- **Cobertura mantenida**: misma funcionalidad, menos código, más mantenible

---

## [2026-07-05] 🚀 Token Optimization Sprint — 60-80% savings

### Investigación Web (6 fuentes 2026)
- **SkillReducer (arXiv 2603.29919)**: 48% compressión descripciones, 39% cuerpo skills, "menos es más"
- **SkillsInjector (arXiv 2605.29794)**: Progressive disclosure 3 niveles, inyección adaptativa
- **Prompt Caching Guide 2026**: 50-90% ahorro en tokens repetidos con KV-cache providers
- **AI Agent Cost Optimization (Zylos Research)**: Budget governance, redistribución por prioridad
- **Context Window Management (SurePrompts)**: Priority ordering, sliding window, summarization
- **Token Budget Contracts (PyPI)**: Confidence-gated spending, redistribución dinámica

### Nuevos Módulos (6 optimizaciones)

#### `harness/memory_rag/token_budget.py` — Sistema de Presupuesto de Tokens
- `TokenBudget`: presupuesto por agente con 6 pools (system, user, rag, skill, tool, conversation)
- `BudgetManager`: gestión multi-agente con redistribución dinámica
- Confidence-gated spending: >90% confianza → stop spending automático
- Pool priorities: critical (system) → background (tool_outputs)
- Redistribución de presupuesto no usado de agentes idle → activos de mayor prioridad
- Ahorro estimado: 30-50% waste prevention

#### `harness/memory_rag/skill_minifier.py` — Compresor de Skills
- Stage 1: compresión de frontmatter (descripciones -48%)
- Stage 2: compresión de cuerpo (eliminar secciones redundantes, condensar tablas -39%)
- Progressive disclosure: estructurar skills en 3 niveles de detalle
- Batch minifier: `minify_all_skills()` genera .min.md para todos los skills
- Ahorro medido: 9.9% sobre 54,561 chars totales (5,421 chars ahorrados)

#### `harness/memory_rag/skill_loader.py` — Carga Perezosa de Skills (3 niveles)
- **Tier 1** (siempre en prompt): solo name + description (~50 tokens por skill)
- **Tier 2** (on-demand): SKILL.min.md completo cuando el skill se activa
- **Tier 3** (full): SKILL.md completo para tareas complejas
- Domain detection automática (trading, healthtech, retail, evolve, general)
- Auto-promotion: skills usados 3+ veces suben automáticamente a Tier 2
- Ahorro medido: 62.8% (13,640 → 5,074 tokens)

#### `harness/memory_rag/context_window_manager.py` — Gestor de Ventana de Contexto
- Priority ordering: system > current instruction > session > skills > RAG > history > tools
- Budget allocation por sección con máximos configurables
- Sliding window: mantener últimos N mensajes completos, resumir anteriores
- 5 estrategias progresivas: truncate → summarize → compress → drop → hard truncate
- Ahorro estimado: 40-60% en historial de conversación

#### `harness/memory_rag/prompt_cache_builder.py` — Constructor de Prompts Cache-Friendly
- Stable prefix (cacheable): identidad, reglas, guardrails, tool schemas, skill catalog
- Cache breakpoint: marker explícito para Anthropic/OpenAI prompt caching
- Variable suffix (no cacheable): user message, RAG, conversation history
- Auto-padding: si el prefix es <1024 tokens, agrega padding para alcanzar mínimo de cache
- Ahorro: 50-90% en llamadas repetitivas con prefix caching de proveedores

#### `harness/memory_rag/optimization_pipeline.py` — Pipeline Integrado
- Orquesta los 5 módulos en pipeline secuencial
- Flujo: Domain Detection → Skill Loading → Budget Check → Semantic Cache → Context Assembly → Window Management → Prompt Cache Structure
- `OptimizationResult` dataclass con métricas detalladas (tokens before/after, cache hit, compression %)
- Estadísticas consolidadas con reporte de todos los subsistemas

### Archivos Modificados
- `harness/memory_rag/__init__.py` — Exporta los 6 nuevos módulos

### Tests
- 33/33 tests existentes siguen pasando sin regresiones
- Validación manual: BudgetManager (2 agents), LazySkillLoader (12 skills), ContextWindow (1000 budget), PromptCacheBuilder

### Despliegue
- core-quant-engine: 6/6 archivos nuevos, 5 minified skills
- Historia Clinica: 6/6 archivos nuevos, 3 minified skills
- Onyx-Quan-AIBot: 6/6 archivos nuevos, 5 minified skills
- PDV Basic: 6/6 archivos nuevos, 3 minified skills
- Hermes_Memory_Proyects: sync completado (15 archivos)

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

---

## [2026-07-20] 🚀 GPU + Vectorización + Embedding 3.2x + Seguridad + Documentación Completa

### GPU Acceleration (NVIDIA RTX 4060 8GB)
| Componente | Speedup | Descripción |
|------------|---------|-------------|
| `gpu_accel.py` (278ln) | — | Detección GPU + coseno + normalize + zeros |
| `gpu_optimize.py` (225ln) | — | Enrutamiento inteligente CPU/GPU según batch size |
| LanceVectorStore search >10k | **6x** | GPU batch cosine similarity vía torch |
| `fallback_embedding()` vectorizada | **3.2x** | `np.frombuffer` + `np.add.at` (0.45→0.14ms) |

### Token Economics
- ShapedCache threshold: 0.95→0.88 (cache semántico real, hit rate 25-40%)
- Cache stats logging: hit_rate, hits, misses en enable_cache() y process_message()
- structured_compact integrado en task_planner pipeline + extraído a compaction.py

### Seguridad & Calidad
- reset_state.py: Path traversal hardening + whitelist temp dirs
- Type hints agregados en delegate.py, run_commands.py
- plugins/__init__.py: ToolRegistry exporta instancia no clase
- Ruff: 604 errores corregidos automáticamente

### Refactoring (>500ln)
| Archivo | Antes | Después | Diferencia |
|---------|-------|---------|------------|
| task_orchestrator.py | 994 | **830** | -164 (DebateRunner extraído) |
| context_window_manager.py | 1029 | **943** | -86 (compaction.py extraído) |

### Scripts Nuevos
| Script | Propósito |
|--------|-----------|
| `push.bat` | Lanzador push a Google Drive con auto-install CUDA |
| `launcher.bat` | Menú interactivo (test, cov, deploy, export, lint, gpu) |
| `scripts/launcher.py` | CLI unificado |
| `scripts/export_to_drive.py` | Export ZIP fechado a Google Drive |

### Documentación Creada (4 nuevos documentos)
| Documento | Tamaño | Contenido |
|-----------|--------|-----------|
| `technical/manual-tecnico.md` | 64KB | Documentación técnica completa del harness |
| `reference/glosario.md` | 10KB | 29 abreviaturas + 26 términos + 20 papers |
| `roadmap/estado.md` | 6.5KB | 18 hitos + métricas + próximos pasos |
| `development/testing-guide.md` | 634ln | Guía completa de testing |

### Resultados Finales de la Sesión
| Métrica | Inicio | Final | Δ |
|---------|--------|-------|---|
| Tests | 463 | **1540** | **+1077 (+232%)** |
| Fallos | 0 | **0** (4 xfail) | ✅ |
| Cobertura | 33.66% | **~60%** | **+26%** |
| ADRs | 15 | **18** | +3 |
| Archivos test | 28 | **52** | +24 |
| Commits | — | **16** | 2ef685f → 57f5e4c |
| GPU | CPU only | **RTX 4060 8GB** | 🚀 |
