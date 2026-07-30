# ADR-0004: Skill Router — Solo Skills Relevantes

## Estado
**FUSIONADO** — Contenido integrado en ADR-0019.

## Contenido Original
Este ADR documentaba la creacion de `SkillRouter` para seleccionar solo los skills relevantes a cada tarea, evitando cargar los 10 skills completos en contexto.

**Decisión original:** Crear SkillRouter que selecciona solo 1-2 skills relevantes por tarea usando matching por keywords + embedding.

**Resultado original:**
- 60-80% menos tokens en skills
- Solo se activan skills del dominio detectado

## Contenido Fusionado En
[ADR-0019: Agent & Skill Optimization](adr0019-agent-skill-optimization-2026.md)

El contenido fue integrado y expandido en ADR-0019, que ahora cubre la optimizacion completa de agentes y skills incluyendo SkillRouter, SkillBundler y SkillMinifier.
