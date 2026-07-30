# ADR-0018: Comparative Analysis ASDT + Traycer

## Estado
**ACEPTADO** — Investigacion completada. Propuestas de mejora priorizadas.

## Contexto
Se analizaron dos proyectos frontier de sistemas multi-agente para identificar mejoras aplicables a Swarmind:

1. **ASDT** (vitualizz/asdt, 251 commits, Go): AI Software Delivery Team — especialistas instalables en Claude Code/OpenCode con memoria compartida via Engram
2. **Traycer** (traycerai/traycer, 797 stars, 468 commits): Nerve Center for Swarmind Coding — orquestación multi-agente con BYOA, Epic mode, unified context

## Analisis Comparativo

| Caracteristica | ASDT | Traycer | Swarmind | Gap |
|---|---|---|---|---|
| **Runtime** | Claude Code / OpenCode | Claude Code / OpenCode / Cursor / Codex | Harness propio (Python) | Swarmind no se integra con IDEs |
| **Memoria persistente** | Engram (cross-session) | Shared context (in-session) | Scoped Context + LanceDB | Sin memoria cross-session tipo Engram |
| **Especialistas** | 8 (PM, Arch, Dev, QA, Sec, UX, Research) | Multi-agent configurable | 8 agentes fijos | Agentes mas configurables |
| **BYOA** | Solo Claude/OpenCode | Si (multi-provider) | Solo Swarmind | Podria soportar otros LLMs |
| **Epic mode** | No | Si (multi-step workflows) | Worktable (debate) | Epic mode para tareas largas |
| **Agent-to-Agent** | Via shared memory | Si (debate y code review) | AgentBus | Comunicacion mas estructurada |
| **Cross-device** | No | Si | No | Pendiente |
| **Lenguaje** | Go | TypeScript (Bun) | Python | - |

## Propuestas de Mejora para Swarmind

### 1. Memoria Cross-Session tipo Engram
**Inspiracion:** ASDT usa Engram como capa de memoria persistente entre sesiones.
**Propuesta:** 
- Swarmind tiene ScopedContext y LanceDB pero la memoria no persiste entre sesiones de forma nativa
- Implementar `PersistentMemory` que serializa ScopedContext a JSON y lo recarga automáticamente
- Ubicacion: `harness/memory_rag/persistent_memory.py`

### 2. Modo Epico (Multi-Step Workflows)
**Inspiracion:** Traycer tiene Epic mode para tareas estructuradas multi-paso.
**Propuesta:**
- Swarmind tiene Worktable para debate, pero no un modo "epico" para tareas largas
- El modo epico ejecutaria: Plan -> Execute -> Review -> Iterate hasta completar
- Usaria el pipeline DAG existente de TaskPlanner + el sistema de debate de Worktable

### 3. Integracion con IDEs (Claude Code / OpenCode)
**Inspiracion:** Tanto ASDT como Traycer se integran con IDEs y herramientas existentes.
**Propuesta:**
- Swarmind funciona como CLI standalone (run.py)
- Crear adaptador MCP para que Swarmind pueda ser invocado desde Claude Code y OpenCode
- Ya tenemos MCPClient/MCPManager, solo falta exponer los agentes como MCP tools

### 4. BYOA (Bring Your Own Agent)
**Inspiracion:** Traycer permite conectar multiples proveedores de agentes.
**Propuesta:**
- Swarmind tiene agentes fijos (coordinator, builder, scientist, guardian, evolve)
- Permitir registrar agentes externos via MCP/A2A protocol
- Ya tenemos A2A router, solo falta estandarizar el registro

### 5. Router de Rutas (like ASDT /asdt command)
**Inspiracion:** ASDT tiene /asdt que analiza el request y sugiere ruta de especialistas.
**Propuesta:**
- Swarmind tiene `auto_route()` en DelegationEngine pero es implicito
- Crear `/route` command que muestre explicitamente la ruta sugerida
- El usuario podria confirmar o modificar antes de ejecutar

## Prioridades de Implementacion

| # | Propuesta | Impacto | Esfuerzo | Prioridad |
|---|-----------|---------|----------|-----------|
| 1 | Memoria Cross-Session | Alto (continuidad) | Bajo (dias) | 🔴 Alta |
| 2 | Modo Epico | Alto (tareas largas) | Medio | 🔴 Alta |
| 3 | Integracion IDE | Alto (adopcion) | Medio | 🟡 Media |
| 4 | BYOA | Medio (flexibilidad) | Alto | 🟡 Media |
| 5 | Router explicito | Bajo (UX) | Bajo | 🟢 Baja |

## Consecuencias
- Swarmind se mantiene como sistema independiente pero gana interoperabilidad
- No se abandona el harness Python (55k lines, 2556 tests)
- Las mejoras son evolutivas: se agregan sin romper existente
- Se prioriza memoria cross-session y modo epico sobre BYOA
