# Como Modificar el Proyecto — AGENTIC Harness

> **Ultima actualizacion:** Julio 2026 · Python 3.10+ · 68 archivos test · 1522 tests · cobertura ~60%

---

## 1. Estructura del Codigo

Todo el codigo fuente vive dentro de `harness/`, dividido en 4 dominios:

| Dominio | Modulos | Proposito |
|---------|---------|-----------|
| `harness/orchestrator/` | **35** | Orquestacion: agent_bus, task_planner, delegation_engine, scheduler, health, self_healing, debate, adaptive_planner, agent_discovery, agent_capsules, confidence_scorer, difficulty_router, federated_memory, hitl_guard, pbt_templates, behavioral_tracer, telemetry, scope_analyzer, etc. |
| `harness/memory_rag/` | **26** | Memoria vectorial: lance_vector_store, embeddings, semantic_cache, context_assembler, context_injector, trajectory_compressor, knowledge_graph, hermes_bridge, legal_analyzer, fts_search, agent_kpi_tracker, skill_router, compaction, etc. |
| `harness/tools_sandbox/` | **4** | MCP Client/Executor/Manager |
| `harness/evolve_loop/` | **10** | Auto-mejora: cognition_sync, evaluator, gepa_mutator, prompt_evolver, self_improver, skill_generator, agent_builder, nudge_system, procedural_memory |
| `harness/tests/` | **68** | Tests + conftest.py + mock_vector_store.py |

**Regla <900LC:** Ningun archivo supera 900 lineas. Si un modulo crece, se divide.

---

## 2. Ejecutar Tests

```bash
pytest                          # Todos
pytest -m "not slow"            # Rapidos (default en cada commit)
pytest --cov=harness            # Con cobertura
pytest harness/tests/test_agent_bus.py -v   # Archivo especifico
pytest -n auto -m "not slow"    # Paralelo (experimental)
```

Marcadores: `unit` (default), `slow` (>1s), `integration` (LanceDB real).

Fixtures globales en `conftest.py`: mock_store (session), vector_store, agent_bus, delegation_engine, context_assembler, hermes_bridge, cognition_sync, semantic_cache, agent_discovery, trajectory_compressor, context_injector.

---

## 3. Estilo y Principios

```bash
ruff check .           # Linter completo
ruff format .          # Formateo automatico
pre-commit run --all-files  # Hooks: compile-check, secret-scan, ruff-lint
```

| Principio | Exigencia |
|-----------|-----------|
| **DocStrings ES-UTF8** | Toda funcion/clase publica documentada con Args/Returns/Raises |
| **WHAT+WHY+WHERE** | Todo except loguea que paso, por que y donde. `except: pass` = FAIL |
| **Clean Code / DRY / KISS / SSOT / YAGNI** | Nombres claros, sin duplicacion, simple, una fuente de verdad, lo minimo necesario |
| **Resilience** | Circuit breakers, timeouts, retry con backoff |
| **Idempotencia** | Operaciones repetibles sin efectos secundarios |
| **CompRoot** | Composition Root unico para inyeccion de dependencias |

---

## 4. Skills del Sistema (29)

`.opencode/skills/` contiene 29 skills en formato `SKILL.md` + `SKILL.min.md`:

**Core:** evolve, hedgefund, architecture, rust-lang  
**Cuantitativo:** quant-trading, alpha-research, risk-execution, math-doc  
**Datos/ML:** data-science, science-doc  
**Frontend/UX:** frontend-uiux, responsive-ui, creative-design  
**Negocio:** business-strategy, communication, project-management  
**Humanidades:** psychology, sociology, linguistics, ethics, behavioral-economics  
**Educacion/Salud/Legal:** education, sustainability, healthtech, legal-doc  
**Infra/Seguridad:** devops-infra, security-audit  
**Retail/Fisica:** pos-retail, physical-sciences
