# Swarmind — Evolutive Multi-Agent System

![Swarmind](/assets/logo.svg)

**Swarmind** is a multi-agent system for orchestration, execution, and continuous self-improvement with 35 contextual skills, multi-level orchestration, GPU acceleration, and token economics.

## Current Status (August 2026)

| Metric | Value |
|--------|-------|
| Tests | 4662 collected (TDD suite) · 75.70% coverage · mutation testing ≥70% |
| Coverage | 75.70% |
| Agents | 23 specialized (100% profiles) |
| Skills | 35 contextual (100% SKILL.md + SKILL.min.md) |
| Orchestrator Modules | 19 packages / 56 modules |
| Memory/RAG Modules | 15 packages / 34 modules |
| Hook Modules | 4 (security_validator, permission_checker, audit_logger, metrics) |
| Security Modules | Zero Trust (TokenManager, PolicyEngine, verify_agent_identity) |
| Multi-Harness Modules | 5 adapters (opencode, claude, codex, cursor, gemini) |
| GPU | RTX 4060 8GB, CUDA 12.6, torch 2.13.0+cu126 (search x10.9, embeddings 41us/msg) |
| Architecture debt (AGR) | 0 files >500 lines in non-test code (32 modules refactored to packages) |
| Token savings | -51% capsules, -40% structured output, -38% cache-shape |
| Vector stores | LanceDB (central) + SQLite-vec (edge) + federated search |
| Observability | OpenTelemetry (traces, metrics, OTLP export) |
| Parallel orchestration | ParallelExecutor native fan-out + governed voting |
| Commits | 304 |
| Lint / dead code | ruff 0 errors, vulture 0 dead code |

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

## What's New in August 2026

The new modules (Multi-Harness Adapter Layer, Hook System, Zero Trust, Federated Vector Search, SQLite-vec Backend, Async TaskOrchestrator) and the **15 papers 2026 implemented** are documented in detail in [Agents & Skills](../es/guide/agentes-y-skills.md#novedades-julio-2026).

## Documentation

- [Philosophy](../es/guide/filosofia.md) — Design principles
- [How to Use](../es/guide/como-usar.md) — Usage tutorial
- [Agents & Skills (complete)](../es/guide/agentes-y-skills.md) — SSOT of agents, skills, modules
- [Swiss Watch Architecture](../es/architecture/swiss-watch.md) — Coordination pattern
- [Dynamic Scaling](../es/architecture/dynamic-scaling.md) — Planning strategies
- [Frontier Techniques](../es/architecture/composicion.md) — 2026 techniques by agent/skill
- [Technical Manual](../es/technical/manual-tecnico.md) — Complete harness technical documentation
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

**Key differentiators:** GPU Acceleration (search x10.9), Token Economics (-51%), Full Governance, Zero Trust, Deterministic Hook System, Multi-Harness (5 runtimes), 4662 tests.

### August 2026 changes

- Full refactor: **32 modules >500 lines into packages** (architecture debt AGR = 0), SOLID corrected in 9 classes.
- **ParallelExecutor**: native parallel fan-out (ThreadPoolExecutor `max_workers=3`) + governed voting.
- **CUDA 12.6 GPU** enabled (torch 2.13.0+cu126): search x10.9, embeddings 41us/msg.
- **Central portable memory SSOT** (`Memory_Proyects` via `MEMORY_ROOT`), 7.5 GB reclaimed, automatic backup.
- **Local Ollama delegation (4-tier)**: simple/RAG/vision tasks with current local models (`qwen3:4b`, `deepseek-r1:8b`, `qwen2.5-coder:7b`, `qwen3-embedding:0.6b`, `qwen3-vl:4b`) — 0 cloud tokens (TKN), automatic cloud fallback.
- **anydoc integration** (`harness/memory_rag/doc_converter.py` + `doc_ingester.py`): binaries → Markdown → RAG with **21 extensions** (pdf/docx/pptx/xlsx/odt/epub/rtf/csv…), lazy `AnyDocConverter` (firecrawl-anydoc>=0.1.9), `DocumentConversionError(path, reason)` without swallowing errors; ingest via `rag_ingest.py --include-docs` or `!rag ingest --docs`.
- **deepseek-harness patterns**: plugin lifecycle (`PluginBase` with `on_load`/`on_unload`/`events`, `ToolRegistry` with injected `event_bus` + automatic `on_{event}` subscription, idempotent `load_all`/`unload_all`) + session replay (`SessionReplay` markdown/json export, `SessionNotFoundError`) — 59 new tests (30 plugin + 29 replay), registry 94%, session_replay 100%.
- Public documentation updated and cleaned up.
