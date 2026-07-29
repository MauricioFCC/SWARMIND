# ADR-0004: Skill Router — Solo Skills Relevantes

## Estado
**ACEPTADO** — Implementado en commit 9c6900e.

## Contexto
Se cargaban los 10 skills en contexto (~500-2000 tokens c/u) independientemente de la tarea.

## Decision
Crear SkillRouter que selecciona solo 1-2 skills relevantes por tarea usando matching por keywords + embedding.

## Resultado
- 60-80% menos tokens en skills
- Solo se activan skills del dominio detectado
