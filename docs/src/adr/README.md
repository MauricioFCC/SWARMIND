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

### Dominios Especificos
- **ADR-0001**: Mejoras base transversales
- **ADR-0006**: Legal-Doc Colombia (RTF+C, derecho comparado)
