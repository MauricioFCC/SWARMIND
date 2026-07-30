# Swarmind — Evolutive Multi-Agent System

![Swarmind](/assets/logo.svg)

**Swarmind** is a multi-agent system for orchestration, execution, and continuous self-improvement with 31 contextual skills, multi-level orchestration, GPU acceleration, and token economics.

## Current Status (July 2026)

| Metric | Value |
|--------|-------|
| Tests | 3420 passing (29 QA + AIFactory verified) |
| Coverage | ~65% (actual 71.56%, target: 80%) |
| ADRs | 32 (all implemented, sequential 0001-0032) |
| Agents | 20 specialized (100% profiles + .min.md) |
| Skills | 31 contextual (100% SKILL.md + SKILL.min.md) |
| Orchestrator Modules | 48 |
| Memory/RAG Modules | 30 |
| Hook Modules | 4 (security_validator, permission_checker, audit_logger, metrics) |
| Security Modules | Zero Trust (TokenManager, PolicyEngine, verify_agent_identity) |
| Multi-Harness Modules | 12 (runtime_detector, converter_base, 5 adapters, CLI) |
| GPU | RTX 4060 8GB (6x search speedup, 3.2x embedding) |
| Token savings | -51% capsules, -40% structured output, -38% cache-shape |
| Projects | 6 active |
| Vector stores | LanceDB, Chroma, Qdrant + SQLite-vec (edge) |
| Federated Search | Parallel 3 backends + MMR re-ranking |
| Observability | OpenTelemetry (traces, metrics, OTLP export) |
| Benchmarks | AgentBenchmark (accuracy, latency, tokens, success) |
| Commits | 200+ |
| Papers implemented | 15 (Gap Analysis 2026) |

Per-module coverage, milestones, and roadmap are documented in [Project Status](../es/roadmap/estado.md).

## Quick Start

Delegate a task to an agent with `@`:

```bash
python harness/run.py "@builder: implementa una API REST en Rust con endpoints /users CRUD"
```

Or without `@` for automatic detection:

```bash
python harness/run.py "investiga papers sobre transformers 2026"
```

System commands: `!health`, `!metrics`, `!skill list`, `!session`, `!reset`, `!help`.

Full tutorial in [How to Use Swarmind](../es/guide/como-usar.md).

## What's New in July 2026

The new modules (Multi-Harness Adapter Layer, Hook System, Zero Trust, Federated Vector Search, SQLite-vec Backend, Async TaskOrchestrator) and the **15 papers 2026 implemented** are documented in detail in [Agents & Skills](../es/guide/agentes-y-skills.md#novedades-julio-2026).

## Documentation

- [Philosophy](../es/guide/filosofia.md) — Design principles
- [How to Use](../es/guide/como-usar.md) — Usage tutorial
- [Agents & Skills (complete)](../es/guide/agentes-y-skills.md) — SSOT of agents, skills, modules
- [Swiss Watch Architecture](../es/architecture/swiss-watch.md) — Coordination pattern
- [Dynamic Scaling](../es/architecture/dynamic-scaling.md) — Planning strategies
- [Frontier Techniques](../es/architecture/composicion.md) — 2026 techniques by agent/skill
- [Technical Manual](../es/technical/manual-tecnico.md) — Complete harness technical documentation
- [ADR](../es/adr/README.md) — Architecture Decision Records (32 documents)
- [Testing Guide](../es/development/testing-guide.md) — How to write and run tests
- [Glossary](../es/reference/glosario.md) — Terms and abbreviations
- [Roadmap](../es/roadmap/estado.md) — Project status and next steps
- [Development](../es/development/modificar.md) — How to modify and contribute
- [Harness Comparison 2026](../es/reference/comparativa-harness-2026.md) — vs ECC, DeerFlow, CowAgent, CodeWhale

## Architecture

```
Swarmind/
├── .opencode/        ← SSOT (agents, skills, config)
├── harness/          ← Execution engine (orchestrator, memory, hooks, security, tests)
├── docs/src/         ← mdbook documentation
└── pyproject.toml
```

![Architecture Diagram](/assets/diagrams/architecture.svg)

For detailed structure, see [Agents & Skills — File System](../es/guide/agentes-y-skills.md#sistema-de-archivos).

## Benchmark Projects 2026

Swarmind competes with **ECC** (235k stars), **DeerFlow** (78.1k), **CowAgent** (46.2k) and **CodeWhale** (40.2k). The full capability comparison table is in [Harness Comparison 2026](../es/reference/comparativa-harness-2026.md).

**Key differentiators:** GPU Acceleration (6x), Token Economics (-51%), Full Governance, Zero Trust, Deterministic Hook System, Multi-Harness (5 runtimes), 15 papers 2026 implemented, 3420 tests.
