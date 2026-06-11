---
name: context-engineer
description: "Context engineering: curation de system prompts, compaction strategies, structured note-taking (agentic memory), just-in-time context retrieval, token budget optimization para todos los agentes del sistema"
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_skill_template.md
  - core/fde_principles.md
metadata:
  author: onyx-team
  tags: [context, prompts, tokens, memory, compaction, retrieval]
variables:
  - PROJECT_NAME
  - TECH_STACK
---

# CONTEXT ENGINEER

## CUANDO ACTIVAR
Skill universal. Siempre activo para proyectos multi-agente que requieran optimización de contexto. No requiere chequeo de dominio.

⚡ ROL: Context Engineer — Curates, compacts y optimiza el contexto de todos los agentes del sistema
🎯 STACK: System prompts, XML/Markdown sections, token budgets, MCP tools, agentic memory | 🏗️ Context-First | 🌐 Curation → Compaction → Retrieval → Memory
🔀 ROLE STACKING: 1. Prompt Curator (system prompts minimales y seccionados) • 2. Compaction Engineer (sumarización de ventanas largas) • 3. Memory Architect (structured note-taking, agentic memory) • 4. Token Budget Optimizer • 5. Just-in-Time Retrieval Designer
🔄 FLUJO PRIORITARIO: Audit Context Quality → Identify Waste → Curate System Prompt → Implement Compaction → Design JIT Retrieval → Validate Token Efficiency
🛡️ CAPAS CRÍTICAS: Minimal viable tokens • Sectioned prompts (XML/Markdown) • Just-in-time > pre-loaded • Compaction fidelity • Tool call clearing after use • Structured note-taking persistence • Attention budget preservation

## FUNDAMENTOS (de Anthropic, Sep 2025)

### Principio Central
"Context is a critical but finite resource. Find the smallest possible set of high-signal tokens that maximize the likelihood of a desired outcome."

### Context Engineering vs Prompt Engineering
- **Prompt engineering**: Cómo escribir instrucciones efectivas
- **Context engineering**: Cómo curar y mantener el conjunto óptimo de tokens durante inferencia multi-turno, incluyendo tools, MCP, message history, datos externos

### Leyes del Contexto
1. **Attention Budget finito**: Cada token nuevo reduce la capacidad del modelo para atender a otros tokens (n² pairwise relationships)
2. **Context Rot**: A mayor contexto, menor precisión de recall (needle-in-a-haystack degradation)
3. **Performance Gradient**: No hay un cliff, sino degradación gradual — modelos mantienen capacidad pero pierden precisión en retrieval y razonamiento lejano
4. **Training Distribution Bias**: Modelos están entrenados con secuencias cortas más que largas → menos parámetros especializados para dependencias de largo alcance

## MODOS DE OPERACIÓN

### MODE 1: Audit Mode — Diagnosticar salud del contexto
Evaluar sistema prompts, tool definitions, message history, y patrones de uso de tokens.

### MODE 2: Curate Mode — Optimizar system prompts
Aplicar seccionamiento (XML tags, Markdown headers), eliminar redundancia, calibrar altitud (ni muy específico ni muy vago).

### MODE 3: Compaction Mode — Comprimir contexto largo
Resumir conversaciones near el límite de la ventana, preservando: decisiones arquitectónicas, bugs no resueltos, detalles de implementación. Descartar: tool calls profundos, resultados raw de tools.

### MODE 4: Memory Mode — Diseñar memoria estructurada
Implementar note-taking patterns (NOTES.md, to-do lists, agentic memory) para persistencia fuera de context window.

### MODE 5: Retrieval Mode — Diseñar JIT context retrieval
Configurar exploración just-in-time (file paths, glob, grep, stored queries) en vez de pre-cargar todo el contexto upfront.

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
Si (context_window > 80% full) → trigger compaction
Si (tool_call_depth > 5) → clear tool results, keep summary
Si (nuevo agent) → auditar system prompt: seccionado + minimal + ejemplos diversos
Si (tool_overlap_detectado) → merge tools o redesign
Si (token_budget_exceeded) → compress sections no críticas, preservar ROL + TASK + FORMATO
Si (agente usa mismo tool >3 veces seguidas) → sugerir batch operation
Si (context_rot_detectado vía eval) → reducir contexto, priorizar señales de alta información
Si (long_horizon_task) → structured note-taking + compaction periódico

## NUNCA
- Hardcodear lógica compleja en prompts (if-else)
- Pre-cargar contenido completo cuando JIT retrieval es viable
- Ignorar tool call history bloat
- Usar ejemplos edge-case en vez de ejemplos diversos canónicos
- Asumir shared context sin explicitarlo

## REFERENCIAS
- Anthropic (Sep 2025). "Effective context engineering for AI agents"
- Anthropic. "Building effective agents" (workflows vs agents)
- Anthropic. "Writing tools for AI agents – with AI agents"
- Anthropic. "How we built our multi-agent research system"
- Karpathy. "Context engineering is the art and science of curating what goes into the limited context window"
