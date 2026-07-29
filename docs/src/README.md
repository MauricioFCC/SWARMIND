# AGENTIC — Sistema Multi-Agente Evolutivo

**AGENTIC** es un sistema multi-agente de orquestación, ejecución y auto-mejora continua con 31 skills contextuales, orquestación multi-nivel, GPU acceleration y token economics.

## Estado Actual (Julio 2026)

| Metrica | Valor |
|---------|-------|
| Tests | 3400+ passing |
| Cobertura | ~65% (objetivo: 80%) |
| ADRs | 33 (todos implementados) |
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

## Novedades en Julio 2026

### Multi-Harness Adapter Layer
AGENTIC ahora funciona nativamente desde **5 runtimes** sin perder compatibilidad con OpenCode:

| Runtime | Deteccion | Formato |
|---------|-----------|---------|
| **OpenCode** | `.opencode/` + OPENCODE_AGENT_MD | Nativo (SSOT) |
| **Claude Code** | `ANTHROPIC_API_KEY` + `.claude/` | AGENTS.md + settings.json |
| **Codex CLI** | `OPENAI_API_KEY` + `.codex/` | config.toml + prompts/ |
| **Cursor** | `CURSOR_MODE` + `.cursor/` | .cursorrules + agents/ |
| **Gemini CLI** | `GOOGLE_API_KEY` + `.gemini/` | instructions.md |

Uso: `python harness/run.py !harness export --target claude`

### Hook System — Automatizacion Determinista
4 hooks incorporados que el LLM no puede controlar:

| Hook | Tipo | Prioridad | Proposito |
|------|------|-----------|-----------|
| Security Validator | PRE_TOOL | CRITICAL | Bloquea `rm -rf /`, DROP TABLE, etc. |
| Permission Checker | PRE_TOOL | HIGH | Protege .opencode/opencode.json, pyproject.toml |
| Audit Logger | POST_TOOL | NORMAL | Registra toda operacion en .opencode/audit.log |
| Metrics Collector | ON_NOTIFICATION | LOW | Recolecta metricas del sistema |

### Zero Trust Architecture
- **TokenManager**: Tokens HMAC-SHA256 con rotacion automatica
- **PolicyEngine**: Mini-OPA con wildcards y roles
- **verify_agent_identity**: Verificacion multi-paso (token + identidad + permisos)

### Federated Vector Search
Busqueda paralela en **LanceDB + Chroma + Qdrant** con re-ranking MMR.

### SQLite-vec Backend
Backend vectorial portable **sin dependencias externas** (ideal para edge/offline).

### Async TaskOrchestrator
Refactorizado a **asyncio completo** con 4.8x speedup (ADR-0017).

## Documentacion

- [Guia de uso](guide/como-usar.md) — Como delegar tareas a los agentes
- [Agentes y Skills (completo)](guide/agentes-y-skills.md) — Documentacion detallada de todo el sistema
- [Arquitectura](architecture/swiss-watch.md) — Patron Swiss Watch, Dynamic Scaling, Composicion
- [Manual Tecnico](technical/manual-tecnico.md) — Documentacion tecnica completa del harness
- [ADR](adr/README.md) — Architecture Decision Records (33 documentos)
- [Agentes](agents/coordinator.md) — Perfiles de cada agente
- [Skills](skills/registry.md) — Registro completo de skills (31)
- [Testing Guide](development/testing-guide.md) — Como escribir y ejecutar tests
- [Glosario](reference/glosario.md) — Terminos y abreviaturas
- [Roadmap](roadmap/estado.md) — Estado del proyecto y proximos pasos
- [Desarrollo](development/modificar.md) — Como modificar y contribuir
- [Analisis Arquitectura](guide/analisis-arquitectura.md) — Python vs Rust, Monolith vs Microservicios

## Arquitectura

```
AGENTIC/
├── .opencode/                  ← SSOT (fuente unica de verdad)
│   ├── agents/                 → 20 agentes
│   ├── skills/                 → 31 skills (cada uno en su directorio)
│   └── config/                 → configuracion del proyecto
├── .claude/ .codex/ .cursor/ .gemini/  ← GENERADO por multi-harness
├── harness/
│   ├── orchestrator/           → 48 modulos (TaskOrchestrator, AgentBus, etc.)
│   │   ├── multi_harness/      → 12 modulos (runtime_detector, 5 adapters, CLI)
│   │   └── ...
│   ├── memory_rag/             → 30 modulos (StrategicMemory, FederatedSearch, etc.)
│   ├── hooks/                  → 4 modulos (HookRegistry, HookManager, BuiltinHooks)
│   ├── security/               → Zero Trust (TokenManager, PolicyEngine)
│   └── tests/                  → 3400+ tests
├── docs/
│   └── src/                    → mdbook (73 paginas HTML)
│       ├── adr/                → 33 ADRs (0001-0033)
│       ├── agents/             → 20 paginas de agentes
│       ├── skills/             → 31 paginas de skills
│       └── ...
└── pyproject.toml
```

## 15 Papers 2026 Implementados

| Gap | Paper | Implementacion |
|-----|-------|---------------|
| Governance Decay | arXiv:2606.22528 | GovernanceGuard |
| Natural Language Tools | arXiv:2607.03953 | NaturalLanguageToolkit |
| Multi-User Governance | arXiv:2606.21856 | MultiUserGovernance |
| Organizational Science | arXiv:2607.25446 | OrganizationalLayer |
| Learned Adaptive Memory | arXiv:2607.13591 | StrategicMemory |
| ToolGuardian Security | arXiv:2607.21835 | ToolGuardian |
| Strategic Forgetting | arXiv:2607.22562 | StrategicMemory (SF-AMS) |
| Agent Capsules | arXiv:2605.00410 | AgentCapsules (-51% tokens) |
| ReDNA Creative AI | arXiv:2605.28465 | CreativeWorktable |
| Diversity Collapse | arXiv:2604.18005 | Worktable config |
| Structured Output | arXiv:2604.12301 | TokenOptimizer (-40%) |
| DAG Parallelism | arXiv:2606.01533 / arXiv:2604.15186 | Kahn Algorithm in TokenOptimizer |
| Knowledge Graph | arXiv:2605.27864 | KnowledgeGraph |
| Agentic PBT | arXiv:2510.09907 | Hypothesis + PBT Core |
| Legal NLP | SaulLM-7B + MiningLegalBench | LegalAnalyzer |

## Benchmark Projects 2026

| Proyecto | Stars | Lenguaje | Agentes | Skills | Diferenciador |
|----------|-------|----------|---------|--------|---------------|
| **ECC** | 235k | TypeScript | 67 | 281 | Sistema operativo para agentes |
| **DeerFlow** | 78.1k | Python | — | — | SuperAgent de largo horizonte |
| **CowAgent** | 46.2k | Python | — | — | Auto-evolucion, multi-canal |
| **CodeWhale** | 40.2k | Rust | — | — | Fleet execution, multi-provider |
| **AGENTIC** | — | Python | 20 | 31 | GPU + token economics + governance + calidad |

## Diferenciacion AGENTIC

| Capacidad | ECC | CowAgent | CodeWhale | **AGENTIC** |
|-----------|-----|----------|-----------|-------------|
| GPU Acceleration (6x) | ❌ | ❌ | ❌ | **✅** |
| Token Economics (-51%) | ❌ | ❌ | ❌ | **✅** |
| Governance Framework | ❌ | ❌ | ❌ | **✅ GovernanceAgent + GovernanceGuard** |
| Zero Trust Architecture | ❌ | ❌ | ❌ | **✅ TokenManager + PolicyEngine** |
| Hook System (determinista) | ❌ | ❌ | ❌ | **✅ 4 hooks pre/post/on_edit** |
| Multi-Harness (5 runtimes) | ✅ | ❌ | ❌ | **✅** |
| Creative AI (ReDNA) | ❌ | ❌ | ❌ | **✅ CreativeWorktable** |
| Multi-User Governance | ❌ | ❌ | ❌ | **✅ MultiUserGovernance** |
| Organizational Science | ❌ | ❌ | ❌ | **✅ OrganizationalLayer** |
| Natural Language Tools | ❌ | ❌ | ❌ | **✅ NaturalLanguageToolkit** |
| Strategic Memory | ❌ | ❌ | ❌ | **✅ SF-AMS utility-driven** |
| ToolGuardian Security | ❌ | ❌ | ❌ | **✅ ToolGuardian (88% accuracy)** |
| Knowledge Graph | ❌ | ✅ | ❌ | **✅ KnowledgeGraph** |
| Federated Vector Search | ❌ | ❌ | ❌ | **✅ 3 backends + MMR** |
| SQLite-vec (edge) | ❌ | ❌ | ❌ | **✅** |
| OpenTelemetry | ❌ | ❌ | ❌ | **✅ Agent tracer** |
| 3400+ tests | ❌ | ❌ | ❌ | **✅** |
| 33 ADRs documentados | ❌ | ❌ | ❌ | **✅** |
| Async TaskOrchestrator | ❌ | ❌ | ❌ | **✅ 4.8x speedup** |
| Multi-DB Vector | ❌ | ❌ | ❌ | **✅ LanceDB + Chroma + Qdrant** |
