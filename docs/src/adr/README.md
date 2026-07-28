# Architecture Decision Records — AGENTIC

Indice de todas las decisiones arquitectónicas del proyecto.

| # | Titulo | Estado | Commit |
|---|--------|--------|--------|
| 0001 | [Mejoras Base: quality_overrides, max_speed, async, etc.](adr0001-mejoras.md) | ACEPTADO | — |
| 0002 | [Dynamic Scaling — Cuadrilla que Crece](adr0002-dynamic-scaling.md) | ACEPTADO | 908935a |
| 0003 | [ContextInjector: Inyeccion Ultra-Compacta](adr0003-context-injector.md) | ACEPTADO | a1b2c3d |
| 0004 | [Skill Router: Routing por Similitud + Skills YAML](adr0004-skill-router.md) | ACEPTADO | e4f5g6h |
| 0005 | [Memoria Portable: Export/Import de Colecciones](adr0005-memoria-portable.md) | ACEPTADO | i7j8k9l |
| 0006 | [Legal-Doc Colombia: RTF+C + Derecho Comparado](adr0006-legal-doc-colombia.md) | ACEPTADO | m0n1o2p |
| 0007 | [Memoria Estandares + Tecnicas CP y Comprension](adr0007-memoria-estandares.md) | ACEPTADO | 35065ed |
| **0008** | **[Token Economy & Speed Optimization v2026](adr0008-token-economy-speed.md)** | **ACEPTADO** | **2a63327** |
| **0009** | **[Competitive Programming Techniques v2026](adr0009-competitive-programming-2026.md)** | **ACEPTADO** | **2d681c5** |
| **0010** | **[Text Analysis & Processing Techniques v2026](adr0010-text-analysis-2026.md)** | **ACEPTADO** | **fb618ad** |
| **0011** | **[Idempotencia — No Reimplementar si ya Existe](adr0011-idempotencia-principle.md)** | **ACEPTADO** | **a7dcfee** |
| **0012** | **[DocStrings Obligatorios + Error Readability & Actionability](adr0012-docstrings-error-readability.md)** | **ACEPTADO** | **4b99fc4** |
| **0013** | **[Workflow Patterns + PBT Templates + Context Engineering + 3 mas](adr0013-six-new-techniques.md)** | **ACEPTADO** | **152b99f** |
| **0014** | **[Lazy Loading PEP 562 — Cold Start 72x mas rapido](adr0014-lazy-loading.md)** | **ACEPTADO** | **c1ea3fd** |
| **0015** | **[Frontier Agents & Skills 2026 — MetaClaw, AdaptOrch, MuTON, SWE-Master, ShapleyFlow + frontend-uiux](adr0015-frontier-agents-skills-2026.md)** | **ACEPTADO** | **306e9c4** |
| **0016** | **[Parallel Test Execution & Fail-Under Progresivo](adr0016-parallel-testing-fail-under.md)** | **ACEPTADO** | **2ef685f** |
| **0017** | **[PaCoRe Async Concurrency — AsyncAgentBus + asyncio.gather + WAL](adr0017-pacore-async-concurrency.md)** | **IMPLEMENTADO** | **061e114** |
| **0018** | **[Token Economics - Cache Shape + Structured Compaction + WAL](adr0018-token-economics-cache-shape.md)** | **IMPLEMENTADO** | **7e9e8b8** |
| **0019** | **[Agent & Skill Optimization 2026](adr0019-agent-skill-optimization-2026.md)** | **ACEPTADO** | **754b6cb** |
| **0020** | **[MCP + A2A Architecture 2026](adr0020-mcp-a2a-architecture-2026.md)** | **ACEPTADO** | **20933a3** |

## Resumen por Categoria

### Infraestructura y Escalabilidad
- **ADR-0002**: Scaling dinamico 3-11 agentes segun complejidad
- **ADR-0008**: Token economy con 6 mecanismos (-38% tokens, -41% costo, -44% tiempo)

### Memoria y Contexto
- **ADR-0003**: Inyeccion ultra-compacta de contexto (~38 tokens/subtarea)
- **ADR-0005**: Memoria portable entre sesiones (export/import LanceDB)

### Enrutamiento y Skills
- **ADR-0004**: Routing por similitud semantica + catalogo YAML

### Capacidades de Agentes
- **ADR-0007**: 22+ estandares fijos + tecnicas CP y comprension clasicas
- **ADR-0009**: 30+ tecnicas de programacion competitiva 2026 (Stoer-Wagner, SMAWK, HLD, etc.)
- **ADR-0010**: Text analysis 2026 (Doc-Researcher, Arg-LLaDA, discourse parsing)

### Principios Universales
- **ADR-0011**: Idempotencia — si ya esta implementado, no reimplementar; solo mejorar si hay delta demostrable
- **ADR-0012**: DocStrings ES-UTF8 obligatorios + Error Readability & Actionability (WHAT/WHY/WHERE)
- **ADR-0013**: 6 nuevas tecnicas: Workflow Patterns, PBT Templates, Context Engineering, Behavioral Tracing, Architectural Guardrails, Semantic Versioning

### Performance y Optimizacion
- **ADR-0014**: Lazy Loading PEP 562 — cold start 2800ms→39ms (72x faster)
- **ADR-0016**: Parallel test execution con pytest-xdist + fail-under progresivo 59%
- **ADR-0017**: Patron PaCoRe con AsyncAgentBus (asyncio.Queue), debate paralelo (asyncio.gather), WriteAheadLog
- **ADR-0018**: Cache-Shape Discipline (ShapedCache LRU+TTL, -38% tokens), Structured Compaction (struct47, -41%), Failure-Spend Governance

### Testing y Calidad
- **ADR-0016**: 52 archivos de test, 2900+ tests, MockVectorStore session-scoped, slow/integration/unit markers, ruff linting (604 fixes)

### Concurrencia y Coordinacion
- **ADR-0017**: AsyncAgentBus con canales asyncio.Queue, debate paralelo O(n)→O(1), WriteAheadLog con retry+backoff+cancelacion+recovery

### Token Economics
- **ADR-0018**: ShapedCache (LRU+TTL+relevancia), structured_compact integrado en pipeline TaskOrchestrator+TaskPlanner, WriteAheadLog como Failure-Spend Governance

### Agentes y Skills Frontera 2026
- **ADR-0015**: Builder (SWE-Master, BOAD, SWE-World), Scientist (MetaClaw, MARS, Hyperagents), Guardian (MuTON, AdverTest, SWE-Mutation), Coordinator (AdaptOrch, NeuralFSM, MPAC, LAS, StructAgent), Evolve (MetaClaw, MARS, Hyperagents, Memento-Skills)

### Dominios Especificos
- **ADR-0001**: Mejoras base transversales
- **ADR-0006**: Legal-Doc Colombia (RTF+C, derecho comparado)
- **ADR-0015**: Frontend-UIUX skill (Generative UI, Design Systems AI-native, 7 PBT templates UI)

