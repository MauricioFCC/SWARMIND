# Cómo Modificar el Proyecto — AGENTIC Harness

> **Última actualización:** Julio 2026 · Python 3.10+ · 92 archivos test · 2900+ tests · cobertura ~65%

---

## 1. Estructura del Código

Todo el código fuente vive dentro de `harness/`, dividido en dominios:

| Dominio | Módulos | Propósito |
|---------|---------|-----------|
| `harness/orchestrator/` | **39** | Orquestación: agent_bus, task_planner, delegation_engine, scheduler, health, self_healing, debate, adaptive_planner, agent_discovery, agent_capsules, confidence_scorer, difficulty_router, federated_memory, hitl_guard, pbt_templates, behavioral_tracer, telemetry, scope_analyzer, governance_agent, agent_cost_controller, business_context, agent_benchmark, etc. |
| `harness/memory_rag/` | **27** | Memoria vectorial: lance_vector_store, vector_store_adapter, embeddings, semantic_cache, context_assembler, context_injector, trajectory_compressor, knowledge_graph, hermes_bridge, legal_analyzer, fts_search, agent_kpi_tracker, skill_router, compaction, etc. |
| `harness/tools_sandbox/` | **4** | MCP Client/Executor/Manager |
| `harness/evolve_loop/` | **9** | Auto-mejora: cognition_sync, evaluator, gepa_mutator, prompt_evolver, self_improver, skill_generator, agent_builder, nudge_system, procedural_memory |
| `harness/observability/` | **2** | OpenTelemetry: logging, opentelemetry_agent (trazas, métricas, exportación OTLP) |
| `harness/tests/` | **96** | Tests (92 test_*.py + conftest.py + mock_vector_store.py + __init__.py) |

**Nuevos módulos incorporados:**

| Módulo | Archivo | Propósito |
|--------|---------|-----------|
| GovernanceAgent | `orchestrator/governance_agent.py` | Políticas de gobernanza, compliance, auditoría de decisiones multi-agente (ADR-0027) |
| AgentCostController | `orchestrator/agent_cost_controller.py` | Detección de loops infinitos, control de costos de ejecución por agente |
| BusinessContext | `orchestrator/business_context.py` | Glosario de términos de negocio, contexto semántico compartido entre agentes |
| AgentBenchmark | `orchestrator/agent_benchmark.py` | Evaluación de agentes: accuracy, latencia, uso de tokens, tasa de éxito |
| OpenTelemetryAgent | `observability/opentelemetry_agent.py` | Trazabilidad distribuida, spans por operación, métricas, exportación OTLP |
| VectorStoreAdapter | `memory_rag/vector_store_adapter.py` | Abstracción multi-DB: LanceDB, Chroma, Qdrant con conmutación en caliente |

**Regla <900LC:** Ningún archivo supera 900 líneas. Si un módulo crece, se divide.

---

## 2. Ejecutar Tests

```bash
pytest                          # Todos
pytest -m "not slow"            # Rápidos (default en cada commit)
pytest --cov=harness            # Con cobertura
pytest harness/tests/test_agent_bus.py -v   # Archivo específico
pytest -n auto -m "not slow"    # Paralelo (experimental)
```

Marcadores: `unit` (default), `slow` (>1s), `integration` (LanceDB real).

Fixtures globales en `conftest.py`: mock_store (session), vector_store, agent_bus, delegation_engine, context_assembler, hermes_bridge, cognition_sync, semantic_cache, agent_discovery, trajectory_compressor, context_injector, governance_agent, agent_benchmark.

---

## 3. Estilo y Principios

```bash
ruff check .           # Linter completo
ruff format .          # Formateo automático
pre-commit run --all-files  # Hooks: compile-check, secret-scan, ruff-lint
```

| Principio | Exigencia |
|-----------|-----------|
| **DocStrings ES-UTF8** | Toda función/clase pública documentada con Args/Returns/Raises |
| **WHAT+WHY+WHERE** | Todo except loguea qué pasó, por qué y dónde. `except: pass` = FAIL |
| **Clean Code / DRY / KISS / SSOT / YAGNI** | Nombres claros, sin duplicación, simple, una fuente de verdad, lo mínimo necesario |
| **Resilience** | Circuit breakers, timeouts, retry con backoff |
| **Idempotencia** | Operaciones repetibles sin efectos secundarios |
| **CompRoot** | Composition Root único para inyección de dependencias |

---

## 4. Skills del Sistema (30)

`.opencode/skills/` contiene 30 skills en formato `SKILL.md` + `SKILL.min.md` (cobertura 100%):

**Core:** evolve, hedgefund, architecture, rust-lang  
**Cuantitativo:** quant-trading, alpha-research, risk-execution, math-doc  
**Datos/ML:** data-science, science-doc  
**Frontend/UX:** frontend-uiux, responsive-ui, creative-design  
**Negocio:** business-strategy, communication, project-management  
**Humanidades:** psychology, sociology, linguistics, ethics, behavioral-economics  
**Educación/Salud/Legal:** education, sustainability, healthtech, legal-doc  
**Infra/Seguridad:** devops-infra, security-audit  
**Retail/Física:** pos-retail, physical-sciences  
**Marketing:** meta-ads-optimizer
