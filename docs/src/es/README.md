# Swarmind — Sistema Multi-Agente Evolutivo

![Swarmind](/assets/logo.svg)

**Swarmind** es un sistema multi-agente de orquestacion, ejecucion y auto-mejora continua con 35 skills contextuales, orquestacion multi-nivel, GPU acceleration y token economics.

## Estado Actual (Agosto 2026)

| Metrica | Valor |
|---------|-------|
| Tests | 4662 collected (TDD suite) · 75.70% coverage · mutation testing ≥70% |
| Cobertura | 75.70% |
| Agentes | 23 especializados (100% perfiles) |
| Skills | 35 contextuales (100% SKILL.md + SKILL.min.md) |
| Modulos Orchestrator | 19 paquetes / 56 modulos |
| Modulos Memory/RAG | 15 paquetes / 34 modulos |
| Modulos Hooks | 4 (security_validator, permission_checker, audit_logger, metrics) |
| Modulos Security | Zero Trust (TokenManager, PolicyEngine, verify_agent_identity) |
| Modulos Multi-Harness | 5 adapters (opencode, claude, codex, cursor, gemini) |
| GPU | RTX 4060 8GB, CUDA 12.6, torch 2.13.0+cu126 (search x10.9, embeddings 41us/msg) |
| Deuda arquitectura (AGR) | 0 archivos >500 lineas en codigo no-test (32 modulos refactor a paquetes) |
| Token savings | -51% capsulas, -40% structured output, -38% cache-shape |
| Vector stores | LanceDB (central) + SQLite-vec (edge) + federated search |
| Observabilidad | OpenTelemetry (trazas, metricas, exportacion OTLP) |
| Orquestacion paralela | ParallelExecutor fan-out nativo + voting gobernado |
| Commits | 304 |
| Lint / dead code | ruff 0 errores, vulture 0 dead code |

El detalle de cobertura por modulo, hitos y roadmap esta en [Estado del Proyecto](roadmap/estado.md).

## Quick Start

Delega una tarea a un agente con `@`:

```bash
python harness/run.py "@builder: implementa una API REST en Rust con endpoints /users CRUD"
```

O sin `@` para deteccion automatica:

```bash
python harness/run.py "investiga papers sobre transformers 2026"
```

Comandos del sistema: `!health`, `!metrics`, `!skill list`, `!session`, `!reset`, `!help`.

Tutorial completo en [Como Usar Swarmind](guide/como-usar.md).

## Novedades Agosto 2026

Los modulos nuevos (Multi-Harness Adapter Layer, Hook System, Zero Trust, Federated Vector Search, SQLite-vec Backend, Async TaskOrchestrator) y los **15 papers 2026 implementados** se documentan en detalle en [Agentes y Skills](guide/agentes-y-skills.md#novedades-julio-2026).

## Documentacion

- [Filosofia](guide/filosofia.md) — Principios de diseno
- [Como Usar](guide/como-usar.md) — Tutorial de uso
- [Opcion A — SSOT Global OpenCode](guide/opcion-a-ssot-global.md) — Config global + mirror local + sync automatico
- [Agentes y Skills (completo)](guide/agentes-y-skills.md) — SSOT de agentes, skills, modulos
- [Arquitectura Swiss Watch](architecture/swiss-watch.md) — Patron de coordinacion
- [Dynamic Scaling](architecture/dynamic-scaling.md) — Estrategias de planificacion
- [Tecnicas Frontier](architecture/composicion.md) — Tecnicas 2026 por agente/skill
- [Manual Tecnico](technical/manual-tecnico.md) — Documentacion tecnica del harness
- [Testing Guide](development/testing-guide.md) — Como escribir y ejecutar tests
- [Glosario](reference/glosario.md) — Terminos y abreviaturas
- [Roadmap](roadmap/estado.md) — Estado del proyecto y proximos pasos
- [Desarrollo](development/modificar.md) — Como modificar y contribuir
- [Comparativa Harness 2026](reference/comparativa-harness-2026.md) — vs ECC, DeerFlow, CowAgent, CodeWhale

## Arquitectura

```
Swarmind/
├── .opencode/        ← SSOT (agentes, skills, config)
├── harness/          ← Motor de ejecucion (orchestrator, memory, hooks, security, tests)
├── docs/src/         ← Documentacion mdbook
└── pyproject.toml
```

![Diagrama de Arquitectura](/assets/diagrams/architecture.svg)

Para la estructura detallada, ver [Agentes y Skills — Sistema de Archivos](guide/agentes-y-skills.md#sistema-de-archivos).

## Benchmark Projects 2026

Swarmind compite con **ECC** (235k stars), **DeerFlow** (78.1k), **CowAgent** (46.2k) y **CodeWhale** (40.2k). La comparativa completa con tabla de capacidades esta en [Comparativa Harness 2026](reference/comparativa-harness-2026.md).

**Diferenciación clave:** GPU Acceleration (search x10.9), Token Economics (-51%), Governance completo, Zero Trust, Hook System determinista, Multi-Harness (5 runtimes), 4662 tests.

### Cambios Agosto 2026

- Refactor total: **32 modulos >500 lineas a paquetes** (deuda arquitectura AGR = 0), SOLID corregido en 9 clases.
- **ParallelExecutor**: fan-out paralelo nativo (ThreadPoolExecutor `max_workers=3`) + voting gobernado.
- **GPU CUDA 12.6** habilitada (torch 2.13.0+cu126): search x10.9, embeddings 41us/msg.
- **Memoria central SSOT** portable (`Memory_Proyects` via `MEMORY_ROOT`), 7.5 GB liberados, backup automatico.
- **Delegación local Ollama 4-tier**: tareas simples/RAG/visión con modelos locales 2026 (`qwen3:4b`, `deepseek-r1:8b`, `qwen2.5-coder:7b`, `qwen3-embedding:0.6b`, `qwen3-vl:4b`) — 0 tokens cloud (TKN), degradación a cloud automática.
- **Integración anydoc** (`harness/memory_rag/doc_converter.py` + `doc_ingester.py`): binarios → Markdown → RAG con **21 extensiones** (pdf/docx/pptx/xlsx/odt/epub/rtf/csv…), `AnyDocConverter` lazy (firecrawl-anydoc>=0.1.9), `DocumentConversionError(path, reason)` sin tragar errores; ingesta con `rag_ingest.py --include-docs` o `!rag ingest --docs`.
- **Patrones deepseek-harness**: plugin lifecycle (`PluginBase` con `on_load`/`on_unload`/`events`, `ToolRegistry` con `event_bus` DI + suscripción automática `on_{event}`, `load_all`/`unload_all` idempotentes) + session replay (`SessionReplay` export markdown/json, `SessionNotFoundError`) — 59 tests nuevos (30 plugin + 29 replay), registry 94%, session_replay 100%.
- Documentacion publica actualizada y depurada.
