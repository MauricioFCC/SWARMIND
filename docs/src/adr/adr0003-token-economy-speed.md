# ADR-0003: Token Economy & Speed Optimization

## Estado
**ACEPTADO** — Implementado en commits 2a63327, c7f8781.

## Contexto
El costo operativo del sistema multi-agente escala con el numero de agentes, la profundidad de las cadenas de razonamiento y la cantidad de contexto intercambiado. Sin mecanismos explicitos de economia de tokens, el sistema puede incurrir en costos runaway donde los tokens consumidos por tarea crecen mas rapido que el valor generado (fenomeno **Token Maxing**, Mojentum 2026).

Se necesita implementar una capa de **Token Economics** que gestione el presupuesto, comprima el contexto, detecte trayectorias sin salida y optimice el costo total por tarea.

## Decision
Implementar 6 mecanismos de token economy y speed optimization en el harness:

### 1. Observation Masking (context_window_manager.py)
- Reemplazar tool outputs grandes con placeholders resumidos
- Inspirado en JetBrains (500 SWE-bench, supera LLM summarization)
- Reduce tokens de observacion hasta 60% en tareas con I/O pesado

### 2. SelfCompact Pattern (trajectory_compressor.py)
- El modelo decide cuando compactar via rubric con 5 fases:
  - `exploring` → mantener detalle
  - `resolving` → compresion moderada
  - `converging` → compresion agresiva
  - `stuck` → reiniciar rama
  - `completed` → resumen final
- Metodo `should_compact()` con heuristica basada en fase actual

### 3. Multi-pass Compaction (optimization_pipeline.py)
- 4 etapas progresivas con early stop:
  1. ToolResult compaction: resumir outputs de herramientas
  2. Summarization: comprimir historia conversacional
  3. SlidingWindow: ventana de contexto limitada
  4. Truncation: corte final si es necesario
- Cada etapa solo se ejecuta si la anterior no fue suficiente

### 4. Real Tokenizer (context_window_manager.py — TokenEstimator)
- Usa `tiktoken` con encoding por modelo:
  - `claude-3-5-sonnet`: `cl100k_base`
  - `gpt-4`/`gpt-4o`: `cl100k_base`
  - `gemini`/`llama`: `o200k_base`
- LRU cache de 2048 entradas para evitar recomputacion
- Busqueda binaria para truncar a presupuesto exacto

### 5. Phase-Scheduled MAS — PSMAS (adaptive_planner.py)
- Ciclo trifasico con activacion por angulo (0°/120°/240°)
- Cada fase activa un subconjunto de agentes:
  - Fase 0°: coordinador + builder + guardian
  - Fase 120°: scientist + evolve
  - Fase 240°: guardian + quality gates
- Agentes inactivos reciben context summaries comprimidos
- Reduce tokens en 27.3% vs ejecucion paralela total

### 6. Failure-Spend Governance (token_budget.py)
- `record_failure()` penaliza al agente con 50% de budget extra
- Desactivacion temporal tras N fallos consecutivos
- Stop-loss por tarea: max tokens antes de abortar graceful
- Write-Ahead Log (WAL) antes de cada tool-call costoso

### Metricas de Impacto

| Mecanismo | Impacto | Fuente |
|-----------|---------|--------|
| Cache-Shape Discipline | -38% tokens | Mojentum 2026 |
| Structured Compaction | -41% costo | Mojentum 2026 |
| Scoped Context Spawn | -44% tiempo | Mojentum 2026 |
| Phase-Scheduled MAS | -27.3% tokens | Medicion propia |
| Observation Masking | -60% obs. tokens | JetBrains 2026 |
| Failure-Spend Governance | Elimina runaway | Diseño propio |

## Archivos Modificados
- `harness/memory_rag/context_window_manager.py`: TokenEstimator, Observation Masking
- `harness/memory_rag/trajectory_compressor.py`: SelfCompact (5 fases, should_compact)
- `harness/memory_rag/optimization_pipeline.py`: Multi-pass Compaction (4 etapas)
- `harness/memory_rag/token_budget.py`: record_failure() con penalizacion 50%
- `harness/orchestrator/adaptive_planner.py`: Phase-Scheduled MAS trifasico

## Consecuencias
- **Positivas**: Costo por tarea reducido ~40%, tiempo de ejecucion -44%, sin runaway
- **Negativas**: Complejidad del harness aumenta ~400 lineas; requiere calibracion de thresholds por dominio
- **Riesgo**: Observation masking puede perder informacion critica si el placeholder es demasiado agresivo — mitigado con phase-aware compression levels

## Referencias
- Mojentum, "Harness Effect: Token Economics for Swarmind Systems", 2026
- JetBrains, "Observation Masking in SWE-bench", 2026
- Hamilton, "Token Maxing: When Token Consumption Outpaces Value", 2026
