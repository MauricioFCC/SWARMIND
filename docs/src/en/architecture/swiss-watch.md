# Architecture — Swiss Watch Pattern

![Architecture](/assets/diagrams/architecture.svg)

Swarmind's architecture is built on the **Swiss Watch Pattern**: each component operates with precision, predictability, and observability, while collaborating to produce emergent intelligence.

## Layers

1. **User Interface Layer** — CLI, Gateway, IDE Adapters
2. **Orchestration Layer** — TaskOrchestrator, A2A Protocol, Event Bus
3. **Agent Layer** — Coordinator → Builder/Scientist/Guardian/Evolve → sub-agents
4. **Memory & RAG Layer** — LanceDB, Chroma, Qdrant, SQLite-vec
5. **Tools & Security Layer** — MCP Servers, Hooks, Zero Trust

## Agent Hierarchy

![Agents Hierarchy](/assets/diagrams/agents-hierarchy.svg)

The coordinator delegates to 5 specialist agents, each of which can spawn sub-agents for complex tasks.

## Multi-Harness

![Multi-Harness](/assets/diagrams/multi-harness.svg)

Swarmind runs natively on **5 runtimes** (OpenCode, Claude Code, Codex CLI, Cursor, Gemini CLI) through the Multi-Harness Adapter Layer.

## Data Flow

![Data Flow](/assets/diagrams/data-flow.svg)

A user request flows through the orchestrator, which plans the execution, delegates to specialized agents, and consolidates results using the memory and tools layers.

## Hook System

![Hook System](/assets/diagrams/hook-system.svg)

The Hook System provides **deterministic automation** that the LLM cannot bypass. Hooks run at specific lifecycle points (PRE_TOOL, POST_TOOL, ON_NOTIFICATION) and enforce security, permissions, auditing, and metrics collection.
