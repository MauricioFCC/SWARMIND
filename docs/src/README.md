# AGENTIC — Sistema Multi-Agente Evolutivo

**AGENTIC** es un sistema multi-agente de orquestación, ejecución y auto-mejora continua. Combina:

- **8 agentes especializados**: coordinator, builder, scientist, guardian, evolve, evolve-researcher, evolve-engineer, evolve-analyzer
- **30 skills contextuales**: 10 categorías (tecnología, seguridad, negocio, finanzas, ciencia, humanidades, salud, legal, retail, sostenibilidad)
- **30+ técnicas frontier 2026**: MetaClaw, SWE-Master, AdaptOrch, MuTON, ShapleyFlow, PaCoRe, MARS, ReDNA, Agent Capsules, etc.
- **Motor de ejecución Plan-and-Execute** con DAG parallelism, memoria vectorial LanceDB/Chroma/Qdrant, federated memory, knowledge graph
- **GPU Acceleration**: RTX 4060 8GB (6x search speedup, 3.2x embedding)
- **OpenTelemetry integrado**: trazabilidad end-to-end de agentes, spans, métricas y exportación OTLP
- **VectorStoreAdapter**: abstracción multi-DB (LanceDB, Chroma, Qdrant) con conmutación en caliente
- **Creative AI**: Pipeline divergente/convergente ReDNA para generación de ideas
- **Token Economics**: Agent Capsules (-51%), Structured Output (-40%), ShapedCache, DAG parallelism
- **Auto-mejora via ASI-Evolve**: Learn → Design → Experiment → Analyze → Deploy con cognition store persistente
- **Evaluación con benchmarks**: AgentBenchmark para medir accuracy, latencia, uso de tokens y tasa de éxito

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

| Métrica | Valor |
|---------|-------|
| Tests | 2900+ passing (2825 funciones + parametrizados) |
| Cobertura | ~65% (objetivo: 80%) |
| ADRs | 27 (todos implementados) |
| Agentes | 8 especializados |
| Skills | 30 (100% SKILL.md + SKILL.min.md) |
| GPU | RTX 4060 8GB (6x search speedup, 3.2x embedding) |
| Token savings | -51% cápsulas, -40% structured output |
| Proyectos | 6 activos |
| Vector stores | LanceDB, Chroma, Qdrant (vía VectorStoreAdapter) |
| Observabilidad | OpenTelemetry (trazas, métricas, exportación OTLP) |
| Benchmarks | AgentBenchmark (accuracy, latencia, tokens, éxito) |
| Commits | 350+ |
