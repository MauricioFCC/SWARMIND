# AGENTIC — Sistema Multi-Agente Evolutivo

**AGENTIC** es un sistema multi-agente de orquestación, ejecución y auto-mejora continua. Combina:

- **8 agentes especializados**: coordinator, builder, scientist, guardian, evolve, evolve-researcher, evolve-engineer, evolve-analyzer
- **11 skills contextuales**: evolve, hedgefund, quant-trading, alpha-research, risk-execution, math-doc, legal-doc, science-doc, frontend-uiux, auto, science-doc
- **25+ técnicas frontier 2026**: MetaClaw, SWE-Master, AdaptOrch, MuTON, ShapleyFlow, PaCoRe, MARS, etc.
- **Motor de ejecución Plan-and-Execute** con DAG parallelism, memoria vectorial LanceDB, federated memory
- **Auto-mejora via ASI-Evolve**: Learn → Design → Experiment → Analyze con cognition store persistente

## Documentación

- [Guía de uso](guide/como-usar.md) — Cómo delegar tareas a los agentes
- [Arquitectura](architecture/swiss-watch.md) — Patrón Swiss Watch, Dynamic Scaling, Composición
- [Manual Técnico](technical/manual-tecnico.md) — Documentación técnica completa del harness
- [ADR](adr/README.md) — Architecture Decision Records (18 documentos)
- [Agentes](agents/coordinator.md) — Perfiles de cada agente
- [Skills](skills/registry.md) — Registro completo de skills
- [Testing Guide](development/testing-guide.md) — Cómo escribir y ejecutar tests
- [Glosario](reference/glosario.md) — Terminos y abreviaturas
- [Roadmap](roadmap/estado.md) — Estado del proyecto y próximos pasos
- [Desarrollo](development/modificar.md) — Cómo modificar y contribuir

## Estado Actual

| Métrica | Valor |
|---------|-------|
| Tests | 1518 passing (4 xfailed) |
| Cobertura | 59.69% (objetivo: 80%) |
| ADRs | 18 (15 implementados) |
| Agentes | 8 especializados |
| Skills | 11 contextuales |
| Commits | 200+ |
