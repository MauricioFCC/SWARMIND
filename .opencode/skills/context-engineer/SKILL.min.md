---
name: context-engineer
description: "Context engineering: curation de system prompts, compaction strategies, structured note-taking (agentic memory), just-in-time context retrieval, token budget optimization para todos los agentes del sistema"
---

## CUANDO ACTIVAR

## FUNDAMENTOS (de Anthropic, Sep 2025)

### Principio Central

### Context Engineering vs Prompt Engineering

### Leyes del Contexto

## MODOS DE OPERACIÓN

### MODE 1: Audit Mode — Diagnosticar salud del contexto

### MODE 2: Curate Mode — Optimizar system prompts

### MODE 3: Compaction Mode — Comprimir contexto largo

### MODE 4: Memory Mode — Diseñar memoria estructurada

### MODE 5: Retrieval Mode — Diseñar JIT context retrieval

## CHECKLIST INTEGRADO

### Audit de Contexto
- [ ] System prompt organizado en secciones (XML/Markdown)
- [ ] Tools: mínimo set viable, sin overlap funcional
- [ ] Tool calls limpiados después de uso profundo en historial
- [ ] Message history sin tool results raw redundantes
- [ ] Token budget por rol definido y monitorizado
- [ ] No hay hardcoding de lógica frágil en prompts

### Compaction
- [ ] Sumarización preserva: decisiones arquitectónicas, bugs activos, detalles críticos
- [ ] Sumarización descarta: tool calls profundos, outputs raw repetidos
- [ ] Compaction test: recall > 90% de información crítica en traces complejos
- [ ] Fallback: último N mensajes si compactación falla

### Memoria Estructurada
- [ ] NOTAS.md o similar para persistencia entre ciclos
- [ ] To-do lists para tracking de progreso en tareas largas
- [ ] Mapas de exploración (para navegación de codebase)
- [ ] Achievements/key decisions log

### JIT Retrieval
- [ ] File paths como lightweight identifiers (no contenido completo)
- [ ] Primitives: glob, grep, head/tail para análisis progresivo
- [ ] Stored queries para datos estructurados
- [ ] Hybrid: pre-cargar contexto crítico + JIT para el resto

## DECISIONES TÉCNICAS (IF-THEN)

## NUNCA

## REFERENCIAS
