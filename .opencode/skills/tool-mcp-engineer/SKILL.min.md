---
name: tool-mcp-engineer
description: "Tool/MCP engineering: diseño, implementación y mantenimiento del ecosistema de herramientas MCP (Model Context Protocol) que los agentes consumen para interactuar con su entorno"
---

## CUANDO ACTIVAR

## FUNDAMENTOS (de Anthropic, Sep 2025)

### Principio Central

### Reglas de Diseño de Tools

### Common Failure Modes

## MODOS DE OPERACIÓN

### MODE 1: Audit Mode — Evaluar ecosistema actual

### MODE 2: Design Mode — Diseñar tool set óptimo

### MODE 3: Build Mode — Implementar MCP servers

### MODE 4: Document Mode — Escribir ejemplos few-shot

### MODE 5: Monitor Mode — Tracking de uso y calidad

## CHECKLIST INTEGRADO

### Diseño
- [ ] Tool set mínimo viable (no más tools de las necesarias)
- [ ] Sin overlap funcional entre tools
- [ ] Input parameters con nombres y descripciones descriptivas
- [ ] Output format token-efficient
- [ ] Cada tool tiene un propósito único y no ambiguo

### Implementación
- [ ] MCP server con manejo de errores (try/except, fallback)
- [ ] Timeout configurado (>30s con retry 3x + backoff)
- [ ] Logging con trace_id para debugging
- [ ] Validación de input (schemas, tipos, rangos)
- [ ] Circuit breaker para tools externas

### Documentación
- [ ] Descripción clara de cuándo usar la tool
- [ ] Ejemplos diversos (3-5) de uso correcto
- [ ] Edge cases documentados
- [ ] Input/output schema explícito

### Monitoreo
- [ ] Tool selection accuracy tracking
- [ ] Frecuencia de uso por tool
- [ ] Tasa de error por tool
- [ ] Tool bloat alert (cuando tools exceden N)
- [ ] Rotación: archivar tools no usadas >90 días

## DECISIONES TÉCNICAS (IF-THEN)

## NUNCA

## REFERENCIAS
