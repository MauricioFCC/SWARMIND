# Composicion del Sistema

## Capas
1. .opencode/ - Cerebro: agentes, skills, config
   - **agents/**: 5 perfiles (coordinator, builder, scientist, guardian, evolve) con ~25 técnicas frontier 2026
   - **skills/**: 30 skills registrados (en 10 categorias: tecnologia, seguridad, negocio, finanzas, ciencia, humanidades, salud, legal, retail, sostenibilidad)
   - **core/**: base_principles.md (3 niveles, 18 principios + 50+ abreviaturas)
2. harness/ - Motor de ejecucion: orchestrator, memory_rag, tests
   - **orchestrator/**: TaskPlanner (11 templates DAG), TaskOrchestrator (Plan-and-Execute), AsyncAgentBus/AgentBus, DebateOrchestrator (3 estrategias + async), ConfidenceScorer, ShapedCache, WriteAheadLog, workflow_patterns (4 patrones), pbt_templates (7 templates), behavioral_tracer, architectural_guardrails
   - **memory_rag/**: LanceDB vector store, ShapedCache (LRU+TTL), semantic cache, context window manager (+structured_compact), token budget, skill minifier/loader, prompt cache builder, federated memory
   - **tests/**: 2628 tests (66 suites, MockVectorStore session-scoped)
   - **gpu_accel.py**: GPU acceleration module (RTX 4060, 6x search speedup)
   - **gpu_optimize.py**: Smart CPU/GPU routing based on batch size
   - **ADR-0016**: Parallel testing + fail-under 59%
   - **ADR-0017**: PaCoRe async concurrency (AsyncAgentBus, asyncio.gather debate, WAL)
   - **ADR-0018**: Token Economics (ShapedCache -38%, structured_compact -41%, WAL governance)
   - **ADR-0019**: Agent & Skill Optimization (30 skills, routing fix)
   - **ADR-0020**: MCP + A2A Protocol Architecture
   - **ADR-0021**: Frontier Gaps 2026 (Agent Capsules -51%)
   - **ADR-0022**: Frontier Optimization (Knowledge Graph, testing)
   - **ADR-0023**: Creative AI Frameworks (ReDNA, Diversity Collapse)
   - **ADR-0024**: Comparative Analysis ASDT + Traycer
   - **ADR-0025**: Frontier Coding Quality (PBT, Refinement Types)
3. scripts/ - Herramientas: deploy_all, export_archive, session_log, agentic_bridge_sync
4. knowledge/ - Documentos de referencia

## Técnicas Frontier Incorporadas (2026)

### Agentes
| Agente | Técnicas Frontier |
|--------|------------------|
| **builder** | SWE-Master (LSP-driven), BOAD (bandit design), SWE-World (Docker-free), ParaManager, ShapleyFlow, TDAD, TDFlow, PaCoRe, REPOREASON |
| **scientist** | MetaClaw (+32%), MARS (single-cycle), Hyperagents, Memento-Skills, Native Self-Evolution, ERL, POLARIS, ShapleyFlow |
| **guardian** | MuTON/mewt (Trail of Bits), AdverTest, SWE-Mutation, CDBench, UAgent, SWE-ABS, PROBE, SMART |
| **coordinator** | AdaptOrch (12-23%↑), NeuralFSM, MPAC (95%↓), Symphony-Coord, LAS (50.5%↓), StructAgent, PaCoRe, LTS, Helium, AsyncAgentBus, asyncio.gather debate |

### Skills
| Skill | Técnicas Frontier |
|-------|------------------|
| **frontend-uiux** | Generative UI, A2UI/OpenUI, Geeklego 3-tier, StyleSeed 74 rules, Bayesian preference, WiserUI-Bench, 7 PBT templates UI |
| **evolve** | MetaClaw, MARS, Hyperagents, Memento-Skills, Native Evolution, ERL, ASI-Evolve loop, FDE |
| **quant-trading** | AlphaCFG, PIKAN, MeanFieldControl, RL static analysis |

### Principios Universales (base_principles.md)
N1 (7 líneas, siempre): RSF, IDP, ERR, ARQ, SEG, DOC, TST, CMT, FDE, EVO, TKN, WFP, PBT, CEN, BTR, AGR, SVE, MCL, MKS
N2 (19 líneas, budget >70%): Detalle de cada principio
N3 (completo): Checklists detallados por categoría

## Documentación del Proyecto

La documentación completa incluye:

| Sección | Archivos | Propósito |
|---------|----------|-----------|
| **Guía de Uso** | 4 docs | Filosofía, cómo usar, velocidad, estándares |
| **Arquitectura** | 3 docs | Swiss Watch, Dynamic Scaling, Composición |
| **Manual Técnico** | 1 doc (NUEVO) | Documentación técnica completa del harness |
| **Agentes** | 5 docs | Perfiles de cada agente |
| **Skills** | 3 docs | Registro y skills específicos |
| **Desarrollo** | 4 docs (NUEVO testing-guide) | Testing, modificación, commits, export |
| **Referencia** | 1 doc (NUEVO glosario) | Términos y abreviaturas |
| **Roadmap** | 1 doc (NUEVO estado) | Estado del proyecto y próximos pasos |
| **ADRs** | 25 docs | Architecture Decision Records (0001-0025) |
