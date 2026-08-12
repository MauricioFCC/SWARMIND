# Swarmind Multi-Agent Harness

![Swarmind banner](assets/banner.svg)

[![Tests: TDD](https://img.shields.io/badge/TDD-100%25-brightgreen.svg)](harness/tests/)
[![Adversarial](https://img.shields.io/badge/Adversarial-enabled-blueviolet.svg)](harness/validation/)
[![Evolutionary](https://img.shields.io/badge/Evolutionary-enabled-blue.svg)](docs/src/es/roadmap/estado.md)
[![Frontier 2026](https://img.shields.io/badge/Frontier-2026-black.svg)](docs/src/es/roadmap/estado.md)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](pyproject.toml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](.pre-commit-config.yaml)
[![Tests](https://img.shields.io/badge/tests-4414_passing-brightgreen.svg)](harness/tests/)
[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Spanish (es)** is the primary documentation language; this README is in English for GitHub.

Swarmind is a Python multi-agent orchestration harness for coordinating AI coding agents (opencode, Claude Code, Codex) through a single, modular engine. It is 100% TDD, adversarial, evolutionary, and built to the frontier of 2026 practices: a fan-out orchestrator with governed voting, heuristic model routing with fallback, real PBT and mutation validation oracles, central portable memory with vector search, token economics, and CUDA GPU acceleration.

## Contents 📑

- [Quickstart](#quickstart)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Usage](#usage)
- [Memory & Backup](#memory--backup)
- [Token Economics](#token-economics)
- [GPU Acceleration](#gpu-acceleration)
- [Development & Quality Gates](#development--quality-gates)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [License](#license)

## Quickstart

Clone, set up, and verify the harness in a few steps:

```bash
# 1. Clone
git clone https://github.com/MauricioFCC/SWARMIND.git
cd SWARMIND

# 2. Auto-setup (verifies Python 3.12+, installs uv, runs uv sync, syncs to opencode global, creates central memory)
python scripts/setup_swarmind.py

# 3. Run the test suite
uv run python -m pytest harness/tests/ -q

# 4. Optional: enable CUDA GPU acceleration (reinstalls the torch CUDA wheel)
python scripts/enable_gpu.py

# 5. Launch the interactive menu
launcher.bat   # Windows
# or: python -m harness
```

## Features

### Core Orchestration
- ParallelExecutors with native fan-out (`harness/orchestrator/parallel_executor.py`, `ThreadPoolExecutor`, `max_workers=3`) and governed voting (gate score ≥ 70 and confidence < 0.7, N=3). Inspired by the 2026 ORCA analysis: stablyai/orca was evaluated and discarded as a tool; its parallelism/voting was adopted natively instead.
- Task planning and orchestration, agent bus, MARS scheduler, MetaClaw, adaptive planning, debate orchestration, worktable, and workflows.
- `harness/run_commands/` package for interactive commands (`!rag`, `!db`, `!iteration`) and a multi-harness layer with adapters + CLI.

### Model Routing & Token Economics
- Heuristic `ModelRouter` (`harness/model_router/complexity_router/`) with small/frontier signals and `route_with_fallback` (confidence < 0.7 falls back to the frontier model).
- `MultiAPIProvider` with failover and health-checks (`harness/model_router/multi_provider/`, `harness/model_router/provider_health/`).
- Token budget SSOT (`token_budgets.yaml`), cache-shape (-38%), structured compaction (-41%), governed voting, and budget enforcement via `TokenBudgetManager`.

### Memory & RAG
- Central portable memory with LanceDB vector store (`harness/memory_rag/lance_vector_store.py`), semantic cache, SQLite-vec adapter (edge/offline backend), federated search, context window management, and `shapley_flow` optimization.
- `AgentKPITracker`, compression strategies, context assembler, token budget managers, and skill loader.

### Validation (PBT & Mutation Oracles)
- `harness/validation/pbt_stage.py`: a real Hypothesis oracle running in a subprocess with 5 invariants (no_crash, returns_value, output_list, deterministic, commutative).
- `harness/validation/mutation_stage.py`: AST mutation with isolated subprocess execution.

### GPU Acceleration
- CUDA 12.6, RTX 4060 8GB, torch 2.13.0+cu126.
- `harness/gpu_accel.py` + `harness/gpu_optimize.py` with measured speedups: vector search **x10.9 (10k)**, **x9.2 (100k)**, and embeddings at **41µs/msg**.
- `scripts/enable_gpu.py` reinstalls the torch CUDA wheel after every `uv sync`.

### Developer Experience
- One-command setup (`scripts/setup_swarmind.py`) and config menu (`config_swarmind.py`).
- CPU-only PyPI torch wheel replaced by the CUDA wheel through a single script, portable across Linux/Mac/Windows.
- Full test suite, ruff-clean code, zero dead code (vulture), and zero architecture debt.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        AGENTS LAYER                          │
│        opencode · Claude Code · Codex (multi-harness)       │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                 ORCHESTRATION LAYER                          │
│  harness/orchestrator/                                       │
│   parallel_executor (fan-out + voting) · task_orchestrator   │
│   task_planner · agent_bus · mars_scheduler · metaclaw       │
│   debate_orchestrator · workflows · worktable                │
│   run_commands/ (commands) · multi_harness (adapters+cli)    │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│               MODEL ROUTING LAYER                            │
│  harness/model_router/                                       │
│   complexity_router (small/frontier) · route_with_fallback   │
│   multi_provider (failover + health-checks) · provider_health│
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    MEMORY & RAG LAYER                        │
│  harness/memory_rag/                                         │
│   lance_vector_store · semantic_cache · sqlite_vec_adapter   │
│   federated_search · shapley_flow · context_window_manager   │
│   token_budget · token_budget_manager                        │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    VALIDATION LAYER                          │
│  harness/validation/                                         │
│   pbt_stage.py (Hypothesis oracle, subprocess, 5 invariants) │
│   mutation_stage.py (AST mutation, isolated subprocess)      │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    ACCELERATION LAYER                        │
│  harness/gpu_accel.py · harness/gpu_optimize.py              │
│  CUDA 12.6 · torch 2.13.0+cu126 · RTX 4060 8GB              │
└──────────────────────────────────────────────────────────────┘
```

Each layer is a dedicated package under `harness/`: the orchestration layer coordinates agents with parallel execution and governed voting; the routing layer dispatches requests to small or frontier models with automatic fallback and provider failover; the memory layer centralizes knowledge in a portable vector store; the validation layer enforces quality with real property-based and mutation oracles; and the acceleration layer offloads compute to the GPU where available.

## Installation

### Requirements

- **Python 3.12+**
- **[uv](https://github.com/astral-sh/uv)** as package/dependency manager
- Optional: NVIDIA GPU with CUDA 12.6 (e.g. RTX 4060 8GB)

### Setup

```bash
git clone https://github.com/MauricioFCC/SWARMIND.git
cd SWARMIND
python scripts/setup_swarmind.py
```

`setup_swarmind.py` verifies Python 3.12+, installs uv if missing, runs `uv sync`, syncs the configuration to the opencode global directory, and creates the central memory store. An interactive config menu is available via `config_swarmind.py`.

### GPU (optional)

The PyPI torch wheel resolved by the lockfile is CPU-only on Windows/Linux. After setting up, activate CUDA with:

```bash
python scripts/enable_gpu.py
```

This reinstalls the torch CUDA wheel and verifies it. **Important:** do not run `uv sync` after enabling CUDA, otherwise the CPU wheel is restored and the CUDA binary is lost; re-run `python scripts/enable_gpu.py` after any `uv sync`.

### Portability

The harness is portable across Linux, macOS, and Windows. Path resolution uses a resilient `_safe_home()` that does not depend on `HOME`, and the central memory store plus its backups live under a configurable root.

## Usage

Launch the interactive harness and delegate tasks to agents:

```bash
python -m harness
```

Available entry points include:

- `delegate` — assign a task to a specific coding agent (opencode, Claude Code, Codex).
- `run` — execute a task through the orchestration pipeline.
- `scheduler` — schedule recurring agent runs (`harness/scheduler/`).
- Iteration pipeline — run a full iteration loop: plan, parallel fan-out, governed voting, validation, and memory persistence.

Interactive commands (`harness/run_commands/`):

- `!rag` — query the vector store.
- `!db` — database inspection / maintenance.
- `!iteration` — trigger the iteration pipeline on demand.

## Memory & Backup

Central memory is the single source of truth (SSOT):

- Default root: `~/Documents/Memory_Proyects` (override with `MEMORY_ROOT`).
- Contains `data/lancedb` plus backups.

Resolution priority in `memory_config.py`:

1. `LANCEDB_PATH` environment variable
2. `.swarmind_config.json` (`MEMORY_ROOT`)
3. Legacy `harness/db/lancedb`

Backups are managed with `scripts/backup_memory.py`:

```bash
python scripts/backup_memory.py --list      # list existing backups
python scripts/backup_memory.py --schedule  # register a scheduled backup
```

Duplicated databases were eliminated (7.5 GB reclaimed). The memory layout is portable across Linux, macOS, and Windows via a resilient `_safe_home()` that works without `HOME`.

## Token Economics

- **Model routing**: `harness/model_router/complexity_router/` emits small/frontier signals; `route_with_fallback` sends low-confidence requests (confidence < 0.7) to the frontier model.
- **Governed voting**: `ParallelExecutor` fans out to N=3 agents when the gate score is ≥ 70 and confidence < 0.7, with a budget of `MAX_TOKENS_BY_AGENT × 3`.
- **Token budgets**: budgets are the single source of truth (`token_budgets.yaml`), enforced by `TokenBudgetManager`.
- **Measured savings**: cache-shape -38%, structured compaction -41%.

## GPU Acceleration

The harness auto-detects the GPU via `harness/gpu_accel.py` and optimizes tensor operations with `harness/gpu_optimize.py`.

- Environment: CUDA 12.6, RTX 4060 8GB, torch 2.13.0+cu126.
- Measured speedups:
  - Vector search **x10.9** (10k vectors), **x9.2** (100k vectors)
  - Embeddings **41µs/msg**

Enable it with:

```bash
python scripts/enable_gpu.py
```

**Warning:** never run `uv sync` after enabling CUDA — the lockfile resolves the CPU torch wheel from PyPI and the CUDA binary is lost. Re-run `python scripts/enable_gpu.py` after every `uv sync`.

## Development & Quality Gates

Quality is enforced continuously, not at the end:

- **Test suite**: 4414 passed, 37 skipped, 4 xfailed.
- **Lint**: ruff — all checks passed.
- **Dead code**: vulture — 0 dead code.
- **Architecture debt (AGR)**: 0 files over 500 lines in non-test code; 32 flat modules refactored into packages with re-exporting `__init__.py`; mixins limited to ≤ 2 bases; SOLID corrected in 9 classes.
- **Validation oracles**: real Hypothesis property-based tests (`pbt_stage.py`, 5 invariants) and AST mutation testing (`mutation_stage.py`) run in isolated subprocesses.
- **TDD**: strictly always-on (RED → GREEN → REFACTOR), backed by WAL before expensive runs.

## Project Structure

```
SWARMIND/
├── harness/
│   ├── orchestrator/           # agent_bus, task_planner, task_orchestrator, mars_scheduler,
│   │                           # metaclaw, adaptive_planner, natural_language_tools, tool_guardian,
│   │                           # multi_user_governance, organizational_layer, health, federated_memory,
│   │                           # agent_discovery, debate_orchestrator, worktable, workflows,
│   │                           # multi_harness (adapters+cli), parallel_executor.py
│   ├── model_router/           # complexity_router, multi_provider, provider_health
│   ├── memory_rag/             # lance_vector_store, semantic_cache, sqlite_vec_adapter, federated_search,
│   │                           # agent_kpi_tracker, vector_store_adapter, context_window_manager,
│   │                           # compression_strategies, shapley_flow, optimization_pipeline,
│   │                           # context_assembler, token_budget, token_budget_manager, skill_loader
│   ├── validation/             # pbt_stage.py, mutation_stage.py
│   ├── gpu_accel.py            # CUDA detection + gpu_optimize.py
│   ├── gpu_optimize.py
│   ├── run_commands/           # interactive commands (!rag, !db, !iteration)
│   ├── scheduler/              # scheduled runs
│   ├── db/migrate_engine/      # database migration engine
│   ├── tools_sandbox/mcp_client/
│   ├── aifactory/              # factory, agent_factory
│   ├── guardrails/guardrail_engine/
│   └── evals/eval_factory/
├── scripts/
│   ├── setup_swarmind.py       # one-command setup (Python 3.12+, uv, uv sync, sync global, central memory)
│   ├── enable_gpu.py           # reinstall torch CUDA wheel after uv sync
│   ├── backup_memory.py        # central memory backups (--list / --schedule)
│   ├── config_swarmind.py      # interactive config menu
│   └── sync_opencode_global.py # sync to opencode global
├── docs/
│   ├── src/es/                 # Documentation (Spanish, primary language)
│   │   ├── roadmap/estado.md
│   │   └── guide/, technical/, reference/, skills/
│   ├── src/en/SUMMARY.md
│   └── .MEJORAS_SWARMIND.md
├── CHANGELOG.md
├── pyproject.toml
└── README.md
```

## Documentation

- [Documentation (ES) — primary language](docs/src/es/) — full docs in Spanish, the main documentation language.
- [English summary](docs/src/en/SUMMARY.md)
- [Roadmap](docs/src/es/roadmap/estado.md)
- [CHANGELOG](CHANGELOG.md)
- [Improvements log](docs/.MEJORAS_SWARMIND.md)

## License

[MIT](LICENSE)