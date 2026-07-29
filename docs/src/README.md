# AGENTIC — Sistema Multi-Agente Evolutivo

**AGENTIC** es un sistema multi-agente de orquestación, ejecución y auto-mejora continua. Combina:

- **20 agentes especializados**: coordinator, builder, scientist, guardian, evolve, evolve-researcher, evolve-engineer, evolve-analyzer, architect, backend-engineer, frontend-engineer, mobile-engineer, data-engineer, devops, database-administrator, security-engineer, qa-engineer, reviewer, product-manager, researcher
- **30 skills contextuales**: 10 categorias (tecnologia, seguridad, negocio, finanzas, ciencia, humanidades, salud, legal, retail, sostenibilidad)
- **30+ tecnicas frontier 2026**: MetaClaw, SWE-Master, AdaptOrch, MuTON, ShapleyFlow, PaCoRe, MARS, ReDNA, Agent Capsules, GovernanceGuard, NaturalLanguageToolkit, MultiUserGovernance, OrganizationalLayer, StrategicMemory, ToolGuardian, etc.
- **Motor de ejecucion Plan-and-Execute** con DAG parallelism, memoria vectorial LanceDB/Chroma/Qdrant, federated memory, knowledge graph
- **GPU Acceleration**: RTX 4060 8GB (6x search speedup, 3.2x embedding)
- **OpenTelemetry integrado**: trazabilidad end-to-end de agentes, spans, metricas y exportacion OTLP
- **VectorStoreAdapter**: abstraccion multi-DB (LanceDB, Chroma, Qdrant) con conmutacion en caliente
- **Creative AI**: Pipeline divergente/convergente ReDNA para generacion de ideas
- **Token Economics**: Agent Capsules (-51%), Structured Output (-40%), ShapedCache, DAG parallelism
- **Auto-mejora via ASI-Evolve**: Learn -> Design -> Experiment -> Analyze -> Deploy con cognition store persistente
- **Evaluacion con benchmarks**: AgentBenchmark para medir accuracy, latencia, uso de tokens y tasa de exito

## Documentación

- [Guía de uso](guide/como-usar.md) — Cómo delegar tareas a los agentes
- [Agentes y Skills (completo)](guide/agentes-y-skills.md) — Documentación detallada de todo el sistema
- [Arquitectura](architecture/swiss-watch.md) — Patrón Swiss Watch, Dynamic Scaling, Composición
- [Manual Técnico](technical/manual-tecnico.md) — Documentación técnica completa del harness
- [ADR](adr/README.md) — Architecture Decision Records (27 documentos)
- [Agentes](agents/coordinator.md) — Perfiles de cada agente
- [Skills](skills/registry.md) — Registro completo de skills (30)
- [Testing Guide](development/testing-guide.md) — Cómo escribir y ejecutar tests
- [Glosario](reference/glosario.md) — Términos y abreviaturas
- [Roadmap](roadmap/estado.md) — Estado del proyecto y próximos pasos
- [Desarrollo](development/modificar.md) — Cómo modificar y contribuir
- [Análisis Arquitectura](guide/analisis-arquitectura.md) — Python vs Rust, Monolith vs Microservicios

## Estado Actual

| Metrica | Valor |
|---------|-------|
| Tests | 3350+ passing |
| Cobertura | ~65% (objetivo: 80%) |
| ADRs | 28 (todos implementados) |
| Agentes | 20 especializados (100% perfiles) |
| Skills | 30 contextuales (100% SKILL.md + SKILL.min.md) |
| Modulos Orchestrator | 48 |
| Modulos Memory/RAG | 30 |
| GPU | RTX 4060 8GB (6x search speedup, 3.2x embedding) |
| Token savings | -51% capsulas, -40% structured output |
| Proyectos | 6 activos |
| Vector stores | LanceDB, Chroma, Qdrant (via VectorStoreAdapter) |
| Observabilidad | OpenTelemetry (trazas, metricas, exportacion OTLP) |
| Benchmarks | AgentBenchmark (accuracy, latencia, tokens, exito) |
| Commits | 196+ |
| Papers implementados | 15 (Gap Analysis 2026) |

## Gap Analysis 2026 — 15 Papers Implementados

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

## Benchmark Projects 2026 — Ecosistema

| Proyecto | Stars | Lenguaje | Agentes | Skills | Diferenciador |
|----------|-------|----------|---------|--------|---------------|
| **ECC** | 235k | TypeScript | 67 | 281 | Sistema operativo para agentes, multi-harness, instincts |
| **DeerFlow** | 78.1k | Python | — | — | SuperAgent de largo horizonte (Long-horizon) |
| **CowAgent** | 46.2k | Python | — | — | Auto-evolucion, multi-canal (Web, WeChat, Telegram, Slack) |
| **CodeWhale** | 40.2k | Rust | — | — | Fleet execution, multi-provider, equipos paralelos |
| **AGENTIC** | — | Python | 20 | 30 | GPU acceleration, token economics, governance, calidad |

## Fortalezas Diferenciales de AGENTIC

| Capacidad | ECC | CowAgent | CodeWhale | **AGENTIC** |
|-----------|-----|----------|-----------|-------------|
| GPU Acceleration | ❌ | ❌ | ❌ | **RTX 4060 6x** |
| Token Economics (-51%) | ❌ | ❌ | ❌ | **Capsules + ShapedCache** |
| Governance Framework | ❌ | ❌ | ❌ | **GovernanceAgent + GovernanceGuard** |
| Creative AI (ReDNA) | ❌ | ❌ | ❌ | **CreativeWorktable** |
| Multi-User Governance | ❌ | ❌ | ❌ | **MultiUserGovernance** |
| Organizational Science | ❌ | ❌ | ❌ | **OrganizationalLayer** |
| Natural Language Tools | ❌ | ❌ | ❌ | **NaturalLanguageToolkit** |
| Strategic Memory | ❌ | ❌ | ❌ | **SF-AMS utility-driven** |
| ToolGuardian Security | ❌ | ❌ | ❌ | **ToolGuardian (88% accuracy)** |
| Knowledge Graph | ❌ | ✅ | ❌ | **KnowledgeGraph** |
| Multi-DB Vector | ❌ | ❌ | ❌ | **LanceDB + Chroma + Qdrant** |
| OpenTelemetry | ❌ | ❌ | ❌ | **Agent tracer** |
| Tests | ❌ | ❌ | ❌ | **3350+ tests** |
| Property-Based Testing | ❌ | ❌ | ❌ | **Hypothesis integrado** |
| ADRs documentados | ❌ | ❌ | ❌ | **28 ADRs** |
| Multi-harness (IDEs) | ✅ | ❌ | ❌ | Pendiente |
| Fleet execution | ❌ | ❌ | ✅ | Pendiente (Swarm mode) |
| Skill marketplace | ❌ | ✅ | ❌ | Pendiente |

## Nicho de AGENTIC

AGENTIC ocupa un nicho unico en el ecosistema de harness 2026:

- **Calidad de codigo**: 3350+ tests, PBT, refinement types, 28 ADRs documentados
- **Optimizacion de costos**: token economics (-51% capsulas, -40% structured output), GPU acceleration (6x search)
- **Gobernanza enterprise**: GovernanceAgent, GovernanceGuard, MultiUserGovernance, OrganizationalLayer, SecurityGuard, ToolGuardian, AgentCostController
- **Research-first**: 15 papers 2026 implementados, gap analysis riguroso, validacion estadistica



