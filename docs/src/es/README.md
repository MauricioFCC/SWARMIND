# Swarmind — Sistema Multi-Agente Evolutivo

![Swarmind](/assets/logo.svg)

**Swarmind** es un sistema multi-agente de orquestacion, ejecucion y auto-mejora continua con 31 skills contextuales, orquestacion multi-nivel, GPU acceleration y token economics.

## Estado Actual (Julio 2026)

| Metrica | Valor |
|---------|-------|
| Tests | 3420 passing (29 QA + AIFactory verificados) |
| Cobertura | ~65% (real 71.56%, objetivo: 80%) |
| ADRs | 32 (todos implementados, secuenciales 0001-0032) |
| Agentes | 20 especializados (100% perfiles + .min.md) |
| Skills | 31 contextuales (100% SKILL.md + SKILL.min.md) |
| Modulos Orchestrator | 48 |
| Modulos Memory/RAG | 30 |
| Modulos Hooks | 4 (security_validator, permission_checker, audit_logger, metrics) |
| Modulos Security | Zero Trust (TokenManager, PolicyEngine, verify_agent_identity) |
| Modulos Multi-Harness | 12 (runtime_detector, converter_base, 5 adapters, CLI) |
| GPU | RTX 4060 8GB (6x search speedup, 3.2x embedding) |
| Token savings | -51% capsulas, -40% structured output, -38% cache-shape |
| Proyectos | 6 activos |
| Vector stores | LanceDB, Chroma, Qdrant + SQLite-vec (edge) |
| Federated Search | Paralelo 3 backends + MMR re-ranking |
| Observabilidad | OpenTelemetry (trazas, metricas, exportacion OTLP) |
| Benchmarks | AgentBenchmark (accuracy, latencia, tokens, exito) |
| Commits | 200+ |
| Papers implementados | 15 (Gap Analysis 2026) |

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

## Novedades Julio 2026

Los modulos nuevos (Multi-Harness Adapter Layer, Hook System, Zero Trust, Federated Vector Search, SQLite-vec Backend, Async TaskOrchestrator) y los **15 papers 2026 implementados** se documentan en detalle en [Agentes y Skills](guide/agentes-y-skills.md#novedades-julio-2026).

## Documentacion

- [Filosofia](guide/filosofia.md) — Principios de diseno
- [Como Usar](guide/como-usar.md) — Tutorial de uso
- [Agentes y Skills (completo)](guide/agentes-y-skills.md) — SSOT de agentes, skills, modulos
- [Arquitectura Swiss Watch](architecture/swiss-watch.md) — Patron de coordinacion
- [Dynamic Scaling](architecture/dynamic-scaling.md) — Estrategias de planificacion
- [Tecnicas Frontier](architecture/composicion.md) — Tecnicas 2026 por agente/skill
- [Manual Tecnico](technical/manual-tecnico.md) — Documentacion tecnica del harness
- [ADR](adr/README.md) — Architecture Decision Records (32 documentos)
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

**Diferenciación clave:** GPU Acceleration (6x), Token Economics (-51%), Governance completo, Zero Trust, Hook System determinista, Multi-Harness (5 runtimes), 15 papers 2026 implementados, 3420 tests.
