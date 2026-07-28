# AGENTIC — Sistema Multi-Agente Evolutivo

**AGENTIC** es un sistema multi-agente de orquestación, ejecución y auto-mejora continua. Combina:

- **8 agentes especializados**: coordinator, builder, scientist, guardian, evolve, evolve-researcher, evolve-engineer, evolve-analyzer
- **29 skills contextuales**: 10 categorias (tecnologia, seguridad, negocio, finanzas, ciencia, humanidades, salud, legal, retail, sostenibilidad)
- **30+ técnicas frontier 2026**: MetaClaw, SWE-Master, AdaptOrch, MuTON, ShapleyFlow, PaCoRe, MARS, ReDNA, Agent Capsules, etc.
- **Motor de ejecución Plan-and-Execute** con DAG parallelism, memoria vectorial LanceDB, federated memory, knowledge graph
- **GPU Acceleration**: RTX 4060 8GB (6x search speedup, 3.2x embedding)
- **Creative AI**: Pipeline divergente/convergente ReDNA para generacion de ideas
- **Token Economics**: Agent Capsules (-51%), Structured Output (-40%), ShapedCache, DAG parallelism
- **Auto-mejora via ASI-Evolve**: Learn → Design → Experiment → Analyze → Deploy con cognition store persistente

## Documentación

- [Guía de uso](guide/como-usar.md) — Cómo delegar tareas a los agentes
- [Agentes y Skills (completo)](guide/agentes-y-skills.md) — Documentación detallada de todo el sistema
- [Arquitectura](architecture/swiss-watch.md) — Patrón Swiss Watch, Dynamic Scaling, Composición
- [Manual Técnico](technical/manual-tecnico.md) — Documentación técnica completa del harness
- [ADR](adr/README.md) — Architecture Decision Records (25 documentos)
- [Agentes](agents/coordinator.md) — Perfiles de cada agente
- [Skills](skills/registry.md) — Registro completo de skills (29)
- [Testing Guide](development/testing-guide.md) — Cómo escribir y ejecutar tests
- [Glosario](reference/glosario.md) — Terminos y abreviaturas
- [Roadmap](roadmap/estado.md) — Estado del proyecto y próximos pasos
- [Desarrollo](development/modificar.md) — Cómo modificar y contribuir
- [Analisis Arquitectura](guide/analisis-arquitectura.md) — Python vs Rust, Monolith vs Microservicios

## Estado Actual

| Métrica | Valor |
|---------|-------|
| Tests | 2628 passing (2 flaky pre-existentes) |
| Cobertura | ~65% (objetivo: 80%) |
| ADRs | 25 (todos implementados) |
| Agentes | 8 especializados |
| Skills | 29 (100% minificados) |
| GPU | RTX 4060 8GB (6x search speedup) |
| Token savings | -51% capsulas, -40% structured output |
| Proyectos | 6 activos |
| Commits | 350+ |
