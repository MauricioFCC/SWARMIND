# Roadmap y Estado del Proyecto

> Estado actual del sistema AGENTIC Harness a 2026-07-20.
> Documento vivo que refleja el progreso, hitos y proximos objetivos.

---

## Estado Actual (2026-07-20)

| Metrica | Valor |
|---------|-------|
| **Tests** | 1789 passing, 4 xfailed |
| **Cobertura** | ~65% |
| **ADRs** | 18 (16 implementados, 2 propuestos) |
| **Commits totales** | ~220+ |
| **Archivos fuente** | ~170 Python files |
| **Tiempo full suite** | ~150s |
| **Tiempo sin slow** | ~45s |
| **Tecnicas 2026 integradas** | 20+ |
| **GPU** | RTX 4060 8GB (6x search speedup) |

### Resumen de Cobertura por Modulo

| Modulo | Archivos | Cobertura | Estado |
|--------|----------|-----------|--------|
| Orchestrator | 32 | ~80% | Robusto |
| Memory/RAG | 25 | ~60% | Estable |
| Tests | 52 | N/A | Base solida |
| Evolve Loop | 10 | ~70% | Estable |
| Tools Sandbox | 4 | ~80% | Cubierto (MCP client+manager) |
| Scheduler | 1 | 95% | Robusto |
| Run Commands | 1 | 92% | Robusto |
| Reset State | 1 | ~60% | Mejorado |
| GPU Acceleration | 2 | 100% | Cubierto |

---

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

| Archivo | Lineas | Prioridad | Accion |
|---------|--------|-----------|--------|
| `harness/orchestrator/context_window.py` | ~1029 | Media | Refactor: extraer WindowManager, Strategy |
| `harness/orchestrator/task_orchestrator.py` | ~813 | Media | Refactor: separar MessageHandler, PlanExecutor |
| `harness/tools_sandbox/mcp_executor.py` | ~140 (26% cover) | Alta | Tests faltantes |
| `harness/reset_state.py` | ~70 (43% cover) | Alta | Tests faltantes |

---

## Metricas Clave

| Metrica | Actual | Objetivo | Tendencia |
|---------|--------|----------|-----------|
| Cobertura de tests | ~60% | 80% | :arrow_up: (+26% en sesion) |
| Tests totales | 1540 | ~2000 | :arrow_up: |
| Archivos <900LC | 100% | 100% | :white_check_mark: |
| DocStrings ES-UTF8 | ~95% | 100% | :arrow_up: |
| Tiempo full suite | ~150s | <60s | :arrow_down: |
| Tiempo sin slow | ~45s | <30s | :arrow_down: |
| ADRs implementados | 16/18 | 18/18 | :arrow_up: |
| Commits totales | ~220+ | N/A | :arrow_up: |
| Tecnicas 2026 | 20+ | 25+ | :arrow_up: |
| GPU Speedup | 6x search | 10x full pipeline | :arrow_up: |

### ADRs Pendientes de Implementacion

| ADR | Titulo | Estado |
|-----|--------|--------|
| ADR-0016 | Parallel Testing & Fail-Under | :package: Implementado parcialmente |
| ADR-0017 | PaCoRe Async Concurrency | :package: Implementado parcialmente |
| ADR-0018 | Token Economics Cache Shape | :package: Implementado parcialmente |

---

## Notas de la Version

- **2026-07-20 (final)**: GPU acceleration (RTX 4060, 6x search, 3.2x embedding). Refactor task_orch 994→830, ctx_window 1029→943. ShapedCache threshold 0.88. Seguridad: path traversal hardening. 1540 tests, ~60% coverage.
- **2026-07-20**: Documentacion completa del sistema. Se anaden glosario, roadmap, y se completa SUMMARY con todas las secciones. Cobertura en ~60% con 1540 tests pasando.
- **2026-07-09**: Frontier Upgrade 2026 con MetaClaw, AdaptOrch, MuTON, SWE-Master, ShapleyFlow.
- **2026-07**: Token Economics v2 con ShapedCache y Structured Compaction. Async coordinator con WAL.
- **2026-06**: Lazy loading PEP 562 (72x mas rapido). 6 nuevas tecnicas (WFP, PBT, CEN, BTR, AGR, SVE).
- **2026-05**: Fundacion del sistema con agentes base, memoria federada, skill router, estandares automaticos.

---

> *Este roadmap se actualiza tras cada hito significativo. Proximas revisiones: semanal.*
