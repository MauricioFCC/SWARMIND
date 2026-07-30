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

> **DEPRECADO** — Este ADR ha sido integrado en ADRs posteriores.
> - Contenido de este ADR ahora forma parte de [ADR-0001](adr0001-mejoras.md) (Fundacion)
> - Ver [SUMMARY.md](../SUMMARY.md) para la estructura actualizada de ADRs.

## Deprecacion
**Fecha:** Julio 2026
**Razon:** Compactacion de ADRs para eliminar fragmentacion.
**Reemplazado por:** ADR-0001 (Fundacion del Sistema)
