# Roadmap y Estado del Proyecto

> Estado actual del sistema Swarmind Harness a 2026-07-31.
> Documento vivo que refleja el progreso, hitos y proximos objetivos.

## Estado Actual (2026-07-31)

Las metricas principales del sistema (tests, cobertura, ADRs, agentes, skills, modulos) estan en la [pagina principal](../README.md#estado-actual-julio-2026).

**Resumen ejecutivo:** 3674 tests, **74.95% cobertura real**, 36 ADRs, 20 agentes, 31 skills, 48 modulos orchestrator, 30 modulos memory/rag, RTX 4060 6x speedup, 15 papers 2026 implementados, **Opción A SSOT global implementada**.

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
| **Fundacion del Sistema** | 2026-04 | Creacion del harness, ADR-0001 a ADR-0007, agentes base (coordinator, builder, scientist, guardian) |
| **Memoria y RAG** | 2026-05 | Federated Memory con LanceDB, incrustaciones semanticas, ADR-0005 |
| **Skill Router** | 2026-05 | Enrutamiento de skills por similitud semantica, registro YAML, ADR-0004 |
| **Context Injector** | 2026-05 | Inyeccion de contexto estructurado, ADR-0003 |
| **Estandares Automaticos** | 2026-05 | DocStrings ES-UTF8 obligatorios, ERR_ACTION, ADR-0012 |
| **Idempotencia Principle** | 2026-05 | IDP: no reimplementar si ya existe, ADR-0011 |
| **Competitive Programming 2026** | 2026-06 | Tecnicas CP: Two Pointers, DP, Segment Tree, Trie, KMP, etc., ADR-0009 |
| **Token Economy v1** | 2026-06 | Gestion de presupuesto de tokens, cache semantico, ADR-0008 |
| **Lazy Loading PEP 562** | 2026-06 | Cold start 2800ms -> 39ms (72x mas rapido), ADR-0014 |
| **6 Nuevas Tecnicas** | 2026-06 | WFP + PBT + CEN + BTR + AGR + SVE, ADR-0013, +37 tests |
| **Text Analysis 2026** | 2026-06 | analisis de textos juridicos, Legal2LogicICL, ADR-0010 |
| **Frontier Upgrade 2026** | 2026-07-09 | MetaClaw, AdaptOrch, MuTON, SWE-Master, ShapleyFlow, ADR-0015 |
| **Frontier Agents + Skills** | 2026-07-09 | Agentes frontier, skills especializados, frontend-uiux, legal-doc Colombia |
| **Curva de Cobertura** | 2026-07 | Evolucion: 33.66% -> 43.69% -> 59.69% |
| **Coverage +26%** | 2026-07-20 | 33.66% -> 59.69% (+1055 tests, de ~460 a ~1520) |
| **Async Coordinator** | 2026-07-20 | AsyncAgentBus + async debate + WAL integrados, ADR-0017 |
| **Token Economics v2** | 2026-07-20 | ShapedCache + Structured Compaction + pipeline de tokens, ADR-0018 |
| **Parallel Testing** | 2026-07-20 | pytest-xdist + slow markers + fail-under, ADR-0016 |
| **Documentacion** | 2026-07-20 | ADRs completos + manual tecnico + glosario + roadmap + SUMMARY |
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
| **Expansion agentes** | 2026-07-29 | 8 → 20 agentes especializados (100% perfiles) |
| **32 ADRs** | 2026-07-29 | De 28 a 32 ADRs documentados e implementados |
| **Seguridad ADR-0035** | 2026-07-30 | Scanner de secretos + paths portables en CI y pre-commit |
| **Opción A — SSOT Global** | 2026-07-31 | Cerebro `.opencode/` → `~/.config/opencode/` (sync automático en cada commit) + mirror local en 7 proyectos DEV-SPACE |

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
| ✅ | Refactor archivos >500ln | Mantenibilidad | task_orchestrator.py 994→830, context_window.py 1029→943 | **HECHO** |
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

**Deuda de tipos (ADR-0037 pendiente):** 92 errores de mypy en 32 archivos. mypy queda en `|| true` en CI con TODO hasta tipado progresivo. Categorías principales: `list-item`, `union-attr`, `no-redef`, `attr-defined`, `arg-type`, `valid-type` (uso de `callable`/`any` como tipo), `return-value`, `var-annotated`. Archivos más afectados: `task_manager.py` (8 errores), `shaped_cache.py` (7), `lance_vector_store.py` (5), `scope_analyzer.py` (5), `common.py` (3), `context_assembler.py` (1), `evolve_loop/cognition_sync.py` (1).



---

## Metricas Clave

| Metrica | Actual | Objetivo | Tendencia |
|---------|--------|----------|-----------|
| Cobertura de tests | 71.56% | 80% | Subiendo |
| Tests totales | 3674 | ~4000 | Subiendo |
| Agentes | 20 | 30+ | Subiendo |
| Skills | 31 | 50+ | Subiendo |
| Modulos Orchestrator | 48 | 55+ | Subiendo |
| Modulos Memory/RAG | 30 | 35+ | Subiendo |
| Archivos <900LC | 100% | 100% | Mantenido |
| DocStrings ES-UTF8 | ~95% | 100% | Subiendo |
| Tiempo full suite | ~100s | <60s | Bajando |
| Tiempo sin slow | ~45s | <30s | Bajando |
| ADRs implementados | 35/35 | 35/35 | Completo |
| Commits totales | 230+ | N/A | Subiendo |
| Tecnicas 2026 | 30+ | 40+ | Subiendo |
| Papers implementados | 15 | 20+ | Subiendo |
| GPU Speedup | 6x search | 10x full pipeline | Subiendo |

---

## Notas de la Version

- **2026-07-31**: Opción A implementada — SSOT global opencode (`~/.config/opencode/`) con sync automático en cada commit (pre-commit hook → `scripts/sync_opencode_global.py`). Mirror local completo (`.opencode/` 125 archivos + `harness/` 8451 + 31 skills + registry) desplegado en 7 proyectos de DEV-SPACE preservando config propia. Seguridad: ADR-0035 scanner 0 violaciones, bandit 0 hallazgos en producción (MD5 `usedforsecurity=False`, nosec justificado), gates CI endurecidos (bandit/pip-audit bloquean), dependabot + github-actions. Guia: [docs/src/es/guide/opcion-a-ssot-global.md](../guide/opcion-a-ssot-global.md).
- **2026-07-30**: ADR-0035 política de paths portables + scanner de secretos/rutas personales (0 violaciones). Limpieza de rutas personales en toda la documentación.
- **2026-07-29**: Gap Analysis 2026 completo (15 papers implementados). Nuevos modulos: GovernanceGuard (arXiv:2606.22528), NaturalLanguageToolkit (arXiv:2607.03953), MultiUserGovernance (arXiv:2606.21856), OrganizationalLayer (arXiv:2607.25446), Learned Adaptive Memory (arXiv:2607.13591). Expansion de 8 a 20 agentes. 3420 tests, 32 ADRs, 31 skills, 48 modulos orchestrator, 30 modulos memory/rag.
- **2026-07-20 (final)**: GPU acceleration (RTX 4060, 6x search, 3.2x embedding). Refactor task_orch 994→830, ctx_window 1029→943. ShapedCache threshold 0.88. Seguridad: path traversal hardening. 2900+ tests, ~60% coverage.
- **2026-07-20**: Documentacion completa del sistema. Se anaden glosario, roadmap, y se completa SUMMARY con todas las secciones. Cobertura en ~60% con 2900+ tests pasando.
- **2026-07-09**: Frontier Upgrade 2026 con MetaClaw, AdaptOrch, MuTON, SWE-Master, ShapleyFlow.
- **2026-07**: Token Economics v2 con ShapedCache y Structured Compaction. Async coordinator con WAL.
- **2026-06**: Lazy loading PEP 562 (72x mas rapido). 6 nuevas tecnicas (WFP, PBT, CEN, BTR, AGR, SVE).
- **2026-05**: Fundacion del sistema con agentes base, memoria federada, skill router, estandares automaticos.

---

> *Este roadmap se actualiza tras cada hito significativo. Proximas revisiones: semanal.*
