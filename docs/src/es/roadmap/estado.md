# Roadmap y Estado del Proyecto

> Estado actual del sistema Swarmind Harness a 2026-08-11.
> Documento vivo que refleja el progreso, hitos y proximos objetivos.

## Estado Actual (2026-08-04)

### Estado 2026-09-06 (ADRs frontera 0065-0067 + llm-grep + gitignore ADRs)

- **ADR-0065 Segundo Cerebro (PROPUESTO)** — overlay `graph_overlay.py` SurrealDB solo aristas, LanceDB sigue SSOT; router local-first → nube solo `is_heavy()`.
- **ADR-0066 Prompt-cache TTL (PROPUESTO)** — prefijo estable + prohibido cambio modelo mid-sesión + `time_to_live_s` (chat 3600 / API-subagente 300) + métrica Effective-Input-Price.
- **ADR-0067 LLM-grep frontera (APLICADO)** — `harness/memory_rag/llm_grep.py`: ripgrep-first → ast-grep condicional → `HybridRetriever` último recurso; salida `ruta:linea` + 2 líneas, dedup `(path,line)`, `GrepBudget`, `RouteReport` con alerta `semantic_ratio>20%`. Tests `test_llm_grep.py` **12 passed**; regresión hybrid **22 passed**; ruff 0.
- **.gitignore**: `docs/src/es/adr/` local-only (segunda capa junto a `.githooks/pre-push`); versionado local explícito con `git add -f`.
- **Deuda doc detectada**: `docs/src/es/adr/README.md` indexa hasta 0041, existen 0042-0067 (26 ADRs sin índice); `docs/src/en/adr/` vacío; `estado.md` cabecera anclada a 2026-08-11.

### Estado 2026-08-18 (arquitecturas RAG frontier + integraciones anydoc + deepseek-harness)

- **Arquitecturas RAG 2026 (5 evaluadas, FRS)**:
  - **Hibrido (dense + sparse) IMPLEMENTADO** — `harness/memory_rag/hybrid_retriever.py`:
    `HybridRetriever` fusiona vector denso (LanceDB embeddings) y BM25 disperso
    (SQLite FTS5) con **Reciprocal Rank Fusion** (k=60, Cormack 2009); DI sobre
    `FTSSearch` + `LanceVectorStore`; `HybridResult` frozen.
  - **Correctivo (CRAG) IMPLEMENTADO** — `harness/memory_rag/corrective_retriever.py`:
    valida calidad de recuperacion pre-generacion (arXiv:2401.15884); evaluador
    heuristico cero-LLM (score medio + cobertura de terminos); si calidad < 0.30 →
    query rewrite o fallback; reporta `corrective_action`.
  - **GraphRAG CUBIERTO** — `knowledge_graph.py` (grafo metadatos) +
    TokenBudgetRouter (PageRank + TF-IDF); pipeline LLM de entidades = YAGNI.
  - **Agentic RAG CUBIERTO** — orchestrator multi-agente (fan-out + votacion
    gobernada + tools) ya es la capa agentica.
  - **Multimodal PARCIAL** — anydoc convierte binarios (21 extensiones) → Markdown;
    embeddings multimodales nativos = YAGNI.
  - Tests: `test_hybrid_retriever.py` (12) + `test_corrective_retriever.py` (10);
    regresion memory_rag **191 passed**; ruff 0.

### Estado 2026-08-18 (integraciones anydoc + patrones deepseek-harness)

- **Integración anydoc — binarios → Markdown → RAG** (commit 983f93c):
  `harness/memory_rag/doc_converter.py` con Protocol `DocumentConverter` +
  `AnyDocConverter` (lazy, `firecrawl-anydoc>=0.1.9`) y `DOC_EXTENSIONS` con
  **21 extensiones** (pdf, docx, doc, pptx, ppt, xlsx, xls, odt, odp, ods, rtf,
  epub, csv, tsv, html, htm, md, txt, json, yaml, yml). `DocumentChunker` acepta
  converter inyectado (DI) y propaga `DocumentConversionError(path, reason)`.
  Ingesta con `rag_ingest.py --include-docs` o `!rag ingest --docs`.
- **Patrones deepseek-harness — plugin lifecycle + session replay**:
  `PluginBase` con `on_load()`/`on_unload()`/`events` (no-op), `ToolRegistry`
  con `event_bus` DI y suscripción automática `on_{event}`,
  `load_all()`/`unload_all()` idempotentes; `SessionReplay`
  (`harness/observability/session_replay.py`) export markdown/json +
  `SessionNotFoundError`. Demo: `GreeterTool`.
- Suite: **4722 tests** collected; **35 skills** validos
  (`validate_skills.py --strict`); 59 tests nuevos (30 plugin + 29 replay);
  coverage registry 94%, session_replay 100%.

### Estado 2026-08-11 (deuda AGR 0 + GPU CUDA 12.6 + oraculos reales)

Sesion de cierre de deuda estructural. Deuda AGR a 0: 32 modulos >500 lineas
convertidos a paquetes con `__init__.py` re-export backward-compatible, SOL de
herencia corregido en 9 clases, mixins con <=2 bases, lookup dinamico `_rc.` en
run_commands, baseline de tests identico tras el refactor.

- **GPU CUDA 12.6 activa** en RTX 4060 8GB (torch 2.13.0+cu126): speedups
  vector search x10.9 (10k) / x9.2 (100k) y embeddings batch 41us/msg.
- **Fase 1 TDD con oraculos reales**: `pbt_stage.py` con oraculo Hypothesis
  REAL en subprocess (5 invariantes, sin exec()) y `mutation_stage.py` con
  mutacion AST en subprocess aislado.
- **ParallelExecutor**: fan-out nativo (ThreadPoolExecutor max_workers=3) +
  voting gobernado (gate score>=70 y confidence<0.7, N=3, presupuesto
  MAX_TOKENS_BY_AGENTx3) con metricas fan_out_factor/tokens_per_parallel_agent/
  voting_events (aportacion ORCA 2026 evaluada y descartada como herramienta).
- **Memoria central SSOT** (Memory_Proyects, memory_config.py 3 niveles
  LANCEDB_PATH > .swarmind_config.json > legacy, `_safe_home()` resiliente):
  7.5GB de DBs duplicadas eliminadas, portabilidad Linux/Mac/Windows.
- Suite: **4465 passed, 37 skipped, 4 xfailed**, Ruff all checks passed,
  Vulture 0 muerto.

Las metricas principales del sistema (tests, cobertura, agentes, skills, modulos) estan en la [pagina principal](../README.md#estado-actual-julio-2026).

**Resumen ejecutivo:** 4722 tests, 23 agentes, 35 skills, 19 paquetes orchestrator, 14 paquetes memory/rag, RTX 4060 CUDA 12.6 (x10.9 search), 15 papers 2026 implementados, **Opción A SSOT global implementada + memoria central portable (v3.x)**.

**Actualización 2026-08-04 :** IMPLEMENTADO — plugin compaction-context.js (hook experimental.session.compacting), steps:8 en release-ops/token-budget-auditor, Σ-Mem MVP (reliability_memory.py + 22 tests), memoria gobernada MVP (memory_guard.py + 22 tests), abstention_policy en token_budgets.yaml (stop rules CONVOLVE), regla subagentes condensados en coordinator.md; diferidos justificados: setCacheKey/small_model/provider options. Implementados H1-H8 completos — H1 (10 SKILL.min.md con YAML roto reparados + test TestSkillMinFiles), H2 (5 mins API densos recompactados con compile_skills.py: 58-88% → 35-54%), H3 (routing 45 rutas, universal 10→2 agentes), H4 (release-ops deduplicado), H5 (triada evolve -59.9%), H6 (token_budgets.yaml conectado al runtime, 23 tests nuevos), H7 (base_principles N3 bajo demanda, -6.2K tokens/agente), H8 (opencode.json: compaction.prune + tool_output + mcp_timeout). 22/22 agentes con role_budget. PR #7 mergado: CI con checks requeridos lint/test/security, python 3.12, auto-merge funcional.

**Metricas adicionales no incluidas en README:** 196+ commits, 258 archivos Python, suite completa ~100s (sin slow ~45s), 30+ tecnicas 2026 integradas.

### Resumen de Cobertura por Modulo

| Modulo | Archivos | Cobertura | Estado |
|--------|----------|-----------|--------|
| Orchestrator | 48 | ~80% | Robusto |
| Memory/RAG | 30 | ~60% | Estable |
| Tests | 52+ | N/A | Base solida |
| Evolve Loop | 10 | ~70% | Estable |
| Tools Sandbox | 4 | ~80% | Cubierto (MCP client+manager) |
| Scheduler | 1 | 95% | Robusto |
| Run Commands | 1 | 92% | Robusto |
| Reset State | 1 | ~60% | Mejorado |
| GPU Acceleration | 2 | 100% | Cubierto |

## Hitos Alcanzados

| Hito | Fecha | Logro |
|------|-------|-------|
| **Fundacion del Sistema** | 2026-04 | Creacion del harness, decisiones de arquitectura fundacionales, agentes base (coordinator, builder, scientist, guardian) |
| **Memoria y RAG** | 2026-05 | Federated Memory con LanceDB, incrustaciones semanticas |
| **Skill Router** | 2026-05 | Enrutamiento de skills por similitud semantica, registro YAML |
| **Context Injector** | 2026-05 | Inyeccion de contexto estructurado |
| **Estandares Automaticos** | 2026-05 | DocStrings ES-UTF8 obligatorios, ERR_ACTION |
| **Idempotencia Principle** | 2026-05 | IDP: no reimplementar si ya existe |
| **Competitive Programming 2026** | 2026-06 | Tecnicas CP: Two Pointers, DP, Segment Tree, Trie, KMP, etc. |
| **Token Economy v1** | 2026-06 | Gestion de presupuesto de tokens, cache semantico |
| **Lazy Loading PEP 562** | 2026-06 | Cold start 2800ms -> 39ms (72x mas rapido) |
| **6 Nuevas Tecnicas** | 2026-06 | WFP + PBT + CEN + BTR + AGR + SVE, +37 tests |
| **Text Analysis 2026** | 2026-06 | analisis de textos juridicos, Legal2LogicICL |
| **Frontier Upgrade 2026** | 2026-07-09 | MetaClaw, AdaptOrch, MuTON, SWE-Master, ShapleyFlow |
| **Frontier Agents + Skills** | 2026-07-09 | Agentes frontier, skills especializados, frontend-uiux, legal-doc Colombia |
| **Curva de Cobertura** | 2026-07 | Evolucion: 33.66% -> 43.69% -> 59.69% |
| **Coverage +26%** | 2026-07-20 | 33.66% -> 59.69% (+1055 tests, de ~460 a ~1520) |
| **Async Coordinator** | 2026-07-20 | AsyncAgentBus + async debate + WAL integrados |
| **Token Economics v2** | 2026-07-20 | ShapedCache + Structured Compaction + pipeline de tokens |
| **Parallel Testing** | 2026-07-20 | pytest-xdist + slow markers + fail-under |
| **Documentacion** | 2026-07-20 | Decisiones de arquitectura completas + manual tecnico + glosario + roadmap + SUMMARY |
| **GPU Acceleration** | 2026-07-20 | RTX 4060 detectada, gpu_accel.py (278ln), gpu_optimize.py (225ln), 6x search |
| **Refactor >500ln** | 2026-07-20 | task_orchestrator 994→830, context_window 1029→943 |
| **Embedding 3.2x** | 2026-07-20 | fallback_embedding vectorizada con np.frombuffer + np.add.at |
| **ShapedCache threshold** | 2026-07-20 | 0.95→0.88 para cache semantico real |
| **Gap Analysis 2026** | 2026-07-29 | 15 papers implementados, mapeo completo de gaps frontier |
| **GovernanceGuard** | 2026-07-29 | arXiv:2606.22528 — deteccion de governance decay en cadenas multi-agente |
| **NaturalLanguageToolkit** | 2026-07-29 | arXiv:2607.03953 — herramientas de lenguaje natural para agentes |
| **MultiUserGovernance** | 2026-07-29 | arXiv:2606.21856 — gobierno multi-usuario con aislamiento de sesiones |
| **OrganizationalLayer** | 2026-07-29 | arXiv:2607.25446 — ciencia organizacional aplicada a colectivos de agentes |
| **Learned Adaptive Memory** | 2026-07-29 | arXiv:2607.13591 — memoria adaptativa con retencion aprendida |
| **Expansion agentes** | 2026-07-29 | 8 → 22 agentes especializados (100% perfiles) |
| **32 Decisiones de Arquitectura** | 2026-07-29 | De 28 a 32 decisiones de arquitectura documentadas e implementadas |
| **Seguridad Paths Portables** | 2026-07-30 | Scanner de secretos + paths portables en CI y pre-commit |
| **Opción A — SSOT Global** | 2026-07-31 | Cerebro `.opencode/` → `~/.config/opencode/` (sync automático en cada commit) + mirror local en 7 proyectos DEV-SPACE |
| **Oráculos reales PBT/mutation** | 2026-08-11 | `pbt_stage.py` Hypothesis REAL en subprocess (5 invariantes) + `mutation_stage.py` AST aislado + DynamicDAG + WAL (Fase 1 TDD) |
| **GPU CUDA 12.6** | 2026-08-11 | torch cu126 en RTX 4060 8GB, vector search x10.9 (10k) / x9.2 (100k), embeddings 41us/msg, `enable_gpu.py` portable |
| **ParallelExecutor** | 2026-08-11 | Fan-out paralelo nativo + voting gobernado (gate score>=70 ∧ confidence<0.7, N=3) — aportación ORCA 2026 |
| **Memoria central SSOT** | 2026-08-11 | `Memory_Proyects` única DB + backups, 7.5GB de DBs duplicadas eliminadas, portabilidad Linux/Mac/Windows |
| **Deuda AGR 0** | 2026-08-11 | 32 módulos >500 líneas → paquetes con `__init__.py` re-export, SOL corregido en 9 clases, mixins ≤2 bases, baseline de tests idéntico |
| **Delegacion local Ollama 4-tier** | 2026-08-14 | delegación local Ollama 4-tier (fast/quality/embedding/vision) + keep_alive → minimiza tokens cloud |
| **Delegacion local Ollama — final** | 2026-08-14 | modelos 2026 instalados (qwen3:4b, deepseek-r1:8b, qwen2.5-coder:7b, qwen3-embedding:0.6b, qwen3-vl:4b), 38 tests nuevos (21+17), 2 bugs latentes corregidos en _apply_model_routing |
| **Integracion anydoc** | 2026-08-18 | binarios → Markdown → RAG: `DocumentConverter`/`AnyDocConverter` (21 extensiones, `firecrawl-anydoc`), `DocumentChunker` DI + `DocumentConversionError`, `--include-docs` / `!rag ingest --docs` |
| **Plugin lifecycle + session replay** | 2026-08-18 | patrones deepseek-harness: `PluginBase` on_load/on_unload/events, `ToolRegistry` DI + EventBus, `SessionReplay` (markdown/json) — 59 tests, registry 94%, session_replay 100% |

### Evolucion de Cobertura

```
Jul 09:  33.66%  (~460 tests)
Jul 14:  43.69%  (+605 tests, 2ef685f)
Jul 20:  59.69%  (+1522 tests total, cobertura +26%)
Objetivo: 80%    (proximo hito)
```

---

## Proximos Pasos

| Prioridad | Tarea | Impacto | Detalle | Estado |
|-----------|-------|---------|---------|--------|
| **Alta** | Coverage 80% | Calidad | Atacar archivos con cobertura baja: mcp_executor.py, plugins, evolve_loop | 🔄 Pendiente |
| **Alta** | Async pipeline integration | Rendimiento | TaskOrchestrator async completo, integracion con AsyncAgentBus | 🔄 Pendiente |
| **Media** | MCP server per agent | Integracion | Cada agente con su propio servidor MCP para aislamiento | ⏳ Pendiente |
| **Media** | GPU full pipeline | Rendimiento | Integrar GPU en mas puntos del pipeline (semantic cache, agent_bus) | 🔄 Pendiente |
| **Media** | Fix debate tests | Estabilidad | ~20 tests de debate con ERROR por dependencias de orquestador | ⏳ Pendiente |
| **Baja** | Plugins architecture | Extensibilidad | Sistema de plugins para habilidades externas | ⏳ Pendiente |
| **Baja** | Federated Learning | Innovacion | Aprendizaje federado opcional entre instancias | ⏳ Pendiente |
| **Baja** | Benchmark suite | Rendimiento | Benchmarks automatizados de latencia y throughput | ⏳ Pendiente |
| ✅ | Refactor archivos >500ln | Mantenibilidad | 32 módulos → paquetes con `__init__.py` re-export (deuda AGR 0) | **HECHO** |
| ✅ | Session-scoped fixtures | Velocidad tests | MockVectorStore session-scoped creado | **HECHO** |
| ✅ | GPU acceleration | Rendimiento | RTX 4060 + 6x search + embedding 3.2x | **HECHO** |
| ✅ | Coverage MCP + Federated | Calidad | mcp_client 100%, mcp_manager 100%, federated 100% | **HECHO** |
| ✅ | Coverage optimizer+plugins | Calidad | optimization_pipeline 62t, skill_loader 73t, plugins 46t, mcp_executor 68t | **HECHO** |
| ✅ | ShapedCache + threshold | Token Economics | 0.95→0.88 cache semantico real | **HECHO** |

### Legado de Deuda Tecnica

**Archivos de producción a 0% de cobertura (Auditoria 2026-07-31):**

| Archivo | Stmts | Lineas | Prioridad | Accion |
|---------|------:|-------:|-----------|--------|
| `harness/orchestrator/mars_scheduler.py` | 339 | 1141 | Alta | Tests + refactor <900ln |
| `harness/memory_rag/sqlite_vec_adapter.py` | 337 | 837 | Alta | Tests (tras nosec B608) |
| `harness/memory_rag/federated_search.py` | 249 | 865 | Alta | Tests faltantes |
| `harness/orchestrator/metaclaw.py` | 217 | 833 | Alta | Tests (paper 2026 estrella) |
| `harness/evolve_loop/nudge_system.py` | 109 | ~120 | Media | Tests faltantes |
| `harness/gpu_optimize.py` | 87 | ~225 | Media | Tests + integracion real |
| `harness/memory_rag/token_budget_manager.py` | 75 | ~80 | Media | Tests faltantes |
| `harness/memory_rag/sqlite_vec_utils.py` | 54 | ~55 | Media | Tests faltantes |
| `harness/model_router/hermes_adapter.py` | 52 | ~55 | Media | Tests faltantes |
| `harness/benchmarks/bench_*.py` (×5) | 174 | ~200 | Baja | Tests faltantes |
| `harness/__main__.py` | 2 | 4 | Baja | Smoke test entry point |

**Archivos >500 lineas (Auditoria 2026-07-31, objetivo <900LC):**

| Archivo | Lineas | Prioridad | Accion |
|---------|-------:|-----------|--------|
| `harness/orchestrator/mars_scheduler.py` | 1141 | Alta | Extraer ScheduleEngine, ResourceAllocator |
| `harness/aifactory/factory.py` | 905 | Media | Extraer sub-fabricas |
| `harness/memory_rag/federated_search.py` | 865 | Media | Refactor |
| `harness/orchestrator/adaptive_planner.py` | 859 | Media | Refactor |
| `harness/orchestrator/debate_orchestrator.py` | 856 | Media | Refactor |
| `harness/memory_rag/sqlite_vec_adapter.py` | 837 | Media | Refactor |
| `harness/orchestrator/metaclaw.py` | 833 | Media | Refactor |
| `harness/orchestrator/worktable.py` | 829 | Baja | Refactor |
| `harness/scheduler.py` | 811 | Baja | Refactor |
| `harness/memory_rag/agent_kpi_tracker.py` | 804 | Baja | Refactor |

**Tests lentos (>4s, encontrados 2026-07-31):**

| Test | Tiempo | Archivo |
|------|-------:|---------|
| `TestConnectAll::test_connect_all_success` | 8.17s | `test_mcp_manager.py` |
| `TestConnectAll::test_connect_all_some_fail` | 8.15s | `test_mcp_manager.py` |
| `TestTaskOrchestrator::test_broadcast_plan_envia_subtask_especifica` | 5.73s | `test_orchestrator.py` |
| `TestMultiAPIProvider::test_execute_basic` | 4.18s | `test_frontier_improvements.py` |
| `TestConnectAll::test_connect_all_invalidates_index` | 4.10s | `test_mcp_manager.py` |
| `TestLoadServers::test_load_success` | 4.07s | `test_mcp_manager.py` |

**Deuda de tipos (tipado progresivo pendiente):** 92 errores de mypy en 32 archivos. mypy queda en `|| true` en CI con TODO hasta tipado progresivo. Categorías principales: `list-item`, `union-attr`, `no-redef`, `attr-defined`, `arg-type`, `valid-type` (uso de `callable`/`any` como tipo), `return-value`, `var-annotated`. Archivos más afectados: `task_manager.py` (8 errores), `shaped_cache.py` (7), `lance_vector_store.py` (5), `scope_analyzer.py` (5), `common.py` (3), `context_assembler.py` (1), `evolve_loop/cognition_sync.py` (1).



---

## Metricas Clave

| Metrica | Actual | Objetivo | Tendencia |
|---------|--------|----------|-----------|
| Cobertura de tests | 75.70% | 80% | Subiendo |
| Tests totales | 4722 | ~5000 | Subiendo |
| Agentes | 23 | 30+ | Subiendo |
| Skills | 35 | 50+ | Subiendo |
| Modulos Orchestrator | 142 | 150+ | Subiendo |
| Modulos Memory/RAG | 109 | 120+ | Subiendo |
| Archivos <500LC (deuda AGR) | 100% | 100% | Mantenido |
| Archivos >500LC (deuda AGR) | 0 | 0 | Completada |
| DocStrings ES-UTF8 | ~95% | 100% | Subiendo |
| Tiempo full suite | ~100s | <60s | Bajando |
| Tiempo sin slow | ~45s | <30s | Bajando |
| Decisiones de arquitectura | 44/44 | 44/44 | Completo |
| Commits totales | 230+ | N/A | Subiendo |
| Tecnicas 2026 | 30+ | 40+ | Subiendo |
| Papers implementados | 15 | 20+ | Subiendo |
| GPU Speedup | 6x → 10.9x search | 10x full pipeline | Subiendo |

---

## Notas de la Version

- **2026-08-18**: Integraciones (commit 983f93c): **anydoc** — binarios → Markdown → RAG (`DocumentConverter`/`AnyDocConverter` lazy con `firecrawl-anydoc>=0.1.9`, `DOC_EXTENSIONS` 21 extensiones, `DocumentChunker` con converter DI, `DocumentConversionError(path, reason)` sin tragar errores, `rag_ingest.py --include-docs` + `!rag ingest --docs`); **deepseek-harness** — plugin lifecycle (`PluginBase` on_load/on_unload/events, `ToolRegistry` con event_bus DI, suscripción automática `on_{event}`, load_all/unload_all idempotentes, `GreeterTool` demo) + session replay (`SessionReplay` export markdown/json, `SessionNotFoundError`). 59 tests nuevos (30 plugin + 29 replay); coverage registry 94%, session_replay 100%. **4722 tests** collected, **35 skills** validos.
- **2026-08-11**: Deuda AGR 0 — 32 modulos >500 lineas convertidos a paquetes con `__init__.py` re-export backward-compatible (commits e409982 + 545e591, verificado baseline identico). GPU CUDA 12.6 activa (torch 2.13.0+cu126, RTX 4060 8GB): vector search x10.9 (10k) / x9.2 (100k), embeddings batch 41us/msg, `enable_gpu.py` portable, health hardware info (e246998, 826aeda). Fase 1 TDD: oraculos reales PBT/mutation en subprocess, orchestrator DynamicDAG + WAL, test_router 25 tests + fix `_to_model_route()` (407c36d). ParallelExecutor fan-out + voting gobernado (ORCA 2026 evaluado/descartado, 4408944). Memoria central SSOT Memory_Proyects sin DBs paralelas + portabilidad Linux/Mac/Windows, 7.5GB liberados (4e5583e). **4465 passed, 37 skipped, 4 xfailed**, Ruff all checks passed, Vulture 0.
- **2026-08-08**: TDD always-on (engine authority + test-first real + anti-gaming, `test_dependency_map.py` TDAD src↔tests, `test_reinforcement.py` Tester→mutation→Critic; 74 tests nuevos; contrato TDD 2026 en builder/guardian/coordinator). Fase 3 ahorro de tokens: `complexity_router.py` (RouteLLM-style, 26 tests, ahorro ~2x con fallback) + `token_usage_tracker.py` (medición por agente, 39 tests, thread-safe). Documentación concisa (progressive disclosure: resumen en notas, detalle en módulos). **4277+ tests**.
- **2026-08-08**: Fase 1+2 — MCP stateless 2026-07-28 (`connect_stateless` + `server/discover` + catálogos cacheables + headers Mcp-Method/Mcp-Name, 22 tests), OTel GenAI semconv estables (`start_genai_span`, `gen_ai.*`, 15 tests), DeltaChannel durable exec (`delta_channel.py`, 9 tests), Agent Factory on-demand (`agent_factory.py` + `agent_templates.yaml` 8 plantillas + recommender + render Markdown opencode, 29 tests), validador agentskills.io (`skill_frontmatter.py`, 20 tests, 32/32 skills válidos), skills de dominio 2026 (reviewer adversarial + science citas/reproducibilidad + legal vigencia/citas). Fix test-order: TestGenAISemconv con parcheo por `trace_agent.__globals__` (robusto ante `test_lazy_loading`). **4068+ tests**.
- **2026-08-03**: Memoria central portable (v3.x) en `<Documents>/Memory_Proyects` (MEMORY_ROOT) + backup automático con rotación (`backup_memory.py` + tarea programada) + menú de configuración al instalar (`config_swarmind.py`). TDD: 58 tests nuevos en 5 módulos a 0% cobertura. Optimización de tokens: descripciones de agents/skills -57% (3875→1684 tokens). Deuda técnica: test_agent_builder fechas hardcodeadas corregidas. **3937 tests**.
- **2026-07-31**: Opción A implementada — SSOT global opencode (`~/.config/opencode/`) con sync automático en cada commit (pre-commit hook → `scripts/sync_opencode_global.py`). Mirror local completo (`.opencode/` 125 archivos + `harness/` 8451 + 31 skills + registry) desplegado en 7 proyectos de DEV-SPACE preservando config propia. Seguridad: scanner de secretos 0 violaciones, bandit 0 hallazgos en producción (MD5 `usedforsecurity=False`, nosec justificado), gates CI endurecidos (bandit/pip-audit bloquean), dependabot + github-actions. Guia: [docs/src/es/guide/opcion-a-ssot-global.md](../guide/opcion-a-ssot-global.md).
- **2026-07-30**: Política de paths portables + scanner de secretos/rutas personales (0 violaciones). Limpieza de rutas personales en toda la documentación.
- **2026-07-29**: Gap Analysis 2026 completo (15 papers implementados). Nuevos modulos: GovernanceGuard (arXiv:2606.22528), NaturalLanguageToolkit (arXiv:2607.03953), MultiUserGovernance (arXiv:2606.21856), OrganizationalLayer (arXiv:2607.25446), Learned Adaptive Memory (arXiv:2607.13591). Expansion de 8 a 20 agentes. 3420 tests, 31 skills, 48 modulos orchestrator, 30 modulos memory/rag.
- **2026-07-20 (final)**: GPU acceleration (RTX 4060, 6x search, 3.2x embedding). Refactor task_orch 994→830, ctx_window 1029→943. ShapedCache threshold 0.88. Seguridad: path traversal hardening. 2900+ tests, ~60% coverage.
- **2026-07-20**: Documentacion completa del sistema. Se anaden glosario, roadmap, y se completa SUMMARY con todas las secciones. Cobertura en ~60% con 2900+ tests pasando.
- **2026-07-09**: Frontier Upgrade 2026 con MetaClaw, AdaptOrch, MuTON, SWE-Master, ShapleyFlow.
- **2026-07**: Token Economics v2 con ShapedCache y Structured Compaction. Async coordinator con WAL.
- **2026-06**: Lazy loading PEP 562 (72x mas rapido). 6 nuevas tecnicas (WFP, PBT, CEN, BTR, AGR, SVE).
- **2026-05**: Fundacion del sistema con agentes base, memoria federada, skill router, estandares automaticos.

---

> *Este roadmap se actualiza tras cada hito significativo. Proximas revisiones: semanal.*
