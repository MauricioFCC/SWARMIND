# ADR-0001: Mejoras Post-Refactor — Investigación + Implementación

## Estado
Aceptado e implementado parcialmente (P0-P1 completados, P2 propuesto)

## Contexto
Se realizó investigación web sobre papers, metodologías y técnicas de vanguardia
para sistemas multi-agente con el objetivo de identificar mejoras viables para
el proyecto AGENTIC Harness.

## Fuentes consultadas

### Papers 2026 (arXiv)
| Paper | arXiv | Aporte clave |
|-------|-------|-------------|
| **SkillReducer** | 2603.29919 | 48% compresión descripciones, 39% cuerpo skills, "less-is-more" |
| **SkillsInjector** | 2605.29794 | Inyección adaptativa de skills, rendering set-aware, budgeting dinámico |
| **Single-Agent > Multi-Agent** | Princeton NLP 2026 | Single-agent supera multi-agent en 64% de benchmarks |
| **Self-Adaptive LLM Systems** | Microsoft AutoGen 2026 | DAG dinámico, self-healing, adaptive planning |
| **Token Budget Contracts** | PyPI 2026 | Confidence-gated spending, redistribución dinámica |
| **Prompt Caching 2026** | Anthropic/OpenAI | 50-90% ahorro con prefix caching |

### Metodologías aplicadas
- **DRY**: Eliminación de código duplicado (embedding, stats, search patterns)
- **KISS**: Simplificación de interfaces complejas
- **Hexagonal Architecture**: Separación puertos/adaptadores
- **Strategy Pattern**: Persistencia intercambiable (scheduler)
- **Template Method**: StatsMixin unificado
- **Observer**: AgentBus como canal de eventos

## Decisiones

### P0: Unificar schedulers duplicados ✅ (Implementado)
**Problema**: Dos schedulers (`harness/scheduler.py` + `harness/orchestrator/scheduler.py`)
con APIs similares y persistencia diferente.

**Solución**: 
- `BaseScheduler` (ABC) con `add_job/remove_job/list_jobs/get_job/stop`
- `JobStore` (mixin) con persistencia JSON/YAML auto-detectable
- `SimpleScheduler` (cron-based, hereda de root scheduler)
- `LanceScheduler` (LanceDB logging, hereda de orchestrator scheduler)
- Thin wrappers backward-compatibles

**Resultado**: ~250 líneas de duplicación eliminadas, API unificada.

### P0: Fusionar health.py + telemetry.py ✅ (Implementado)
**Problema**: `CognitiveState` (health.py) y `SessionTelemetry` (telemetry.py)
trackeaban el mismo subtask_history, errors, warnings en memoria duplicada.

**Solución**:
- `CognitiveState` delega en `SessionTelemetry` via propiedades
- health.py = health CHECKING, telemetry.py = data RECORDING
- `TelemetryTracker` opcional inyectable en `AgentHealthChecker`

**Resultado**: Eliminada duplicación de datos en memoria.

### P1: Tests para agent_kpi_tracker.py ✅ (Implementado)
**Problema**: 715 líneas, 0% cobertura.

**Solución**: 56 tests cubriendo:
- Dataclass records + to_lancedb_row()
- record_agent_performance, record_skill_effectiveness
- get_dashboard_summary, get_agent_rankings
- Telemetry level filtering (OFF/BASIC/FULL)

**Resultado**: 93% cobertura en agent_kpi_tracker.py, coverage global 32%.

### P1: Subir coverage general ✅ (Implementado)
**Problema**: Coverage 27% (debajo del threshold 30%).

**Solución**: 105 tests nuevos:
- test_agent_kpi_tracker.py: 56 tests
- test_semantic_cache_extended.py: 39 tests (cache expiry, set, stats, clear)
- test_embeddings.py: 10 tests (delegación a common)

**Resultado**: 32.44% coverage (supera threshold 30%).

### P2: Paralelización de debate entre agentes 🔲 (Propuesto)
**Fundamento**: Multi-agent debate mejora accuracy en tareas complejas.
Paper Princeton NLP 2026: single-agent supera multi-agent en 64% de benchmarks,
pero multi-agent añade ~2.1 puntos de precisión al doble de costo.

**Propuesta**:
- `DebateOrchestrator`: Ejecuta N agentes en paralelo sobre la misma tarea
- `DebateStrategy` enum: CONSENSUS (mayoría), CRITIQUE (un agente critica a otro),
  DELIBERATION (debate secuencial con síntesis)
- `DebateResult`: consolidación de respuestas con metadata de confianza
- Configurable: número de agentes, estrategia, threshold de consenso

**Estimación**: ~400 líneas nuevas, 2-3 días.

### P2: Set-aware rendering de skills 🔲 (Propuesto)
**Fundamento**: SkillsInjector (arXiv 2605.29794) muestra que cómo se PRESENTAN
los skills impacta el performance downstream.

**Propuesta**:
- `SetAwareRenderer`: Ajusta descripciones de skills según qué otros skills
  están co-inyectados en el contexto
- `ContextPlanner`: Decide qué skills incluir y en qué orden, basado en
  embeddings de similitud entre skills y la tarea actual
- Adaptive budgeting: número variable de skills según complejidad

**Estimación**: ~500 líneas nuevas, 3-4 días.

### P2: Confidence-gated Early Stopping 🔲 (Propuesto)
**Fundamento**: Token Budget Contracts (PyPI 2026): confidence-gated spending
detiene generación cuando la confianza supera threshold.

**Propuesta**:
- En `TaskOrchestrator.process_completion()`: evaluar confianza del resultado
- Si confianza > 0.95 y todas las subtasks del nivel actual están completas
  con alta confianza, saltar niveles redundantes
- Métrica: `completion_confidence` basada en longitud, coherencia, y
  velocidad de generación

**Estimación**: ~200 líneas nuevas, 1-2 días.

### P3: Debate paralelo con fan-out/fan-in 🔲 (Propuesto)
**Fundamento**: El patrón fan-out/fan-in de TaskPlanner puede extenderse para
ejecutar múltiples agentes en paralelo sobre la MISMA subtarea y consolidar.

**Propuesta**:
- Nuevo template `debate` en SUBTASK_TEMPLATES
- Subtask con `parallel_agents: ["builder", "scientist", "guardian"]`
- `ConsolidationStrategy` enum: MAJORITY_VOTE, WEIGHTED_SCORE, CRITIQUE_SUMMARY

**Estimación**: ~350 líneas nuevas, 2-3 días.

## Consecuencias

### Positivas
- **C1**: Código más mantenible, API única para scheduling
- **C2**: Menor uso de memoria, datos consistentes en health/telemetry
- **C3+I1**: Confianza en el código (287 tests, 32% coverage)
- **P2+**: Arquitectura preparada para escalar a debate multi-agente

### Negativas
- Se incrementó ligeramente el tamaño de health.py (+118 líneas por delegation)
- P2 requiere más investigación en estrategias de debate
- La paralelización de agentes puede incrementar costos de API

### Riesgos
- El debate multi-agente puede añadir latencia significativa
- Single-agent > multi-agent en 64% de casos (Princeton 2026) — la estrategia
  debe elegirse dinámicamente
- SkillsInjector requiere fine-tuning por proyecto

## Referencias
- arXiv:2603.29919 — SkillReducer: Optimizing LLM Agent Skills for Token Efficiency
- arXiv:2605.29794 — SkillsInjector: Dynamic Skill Context Construction for LLM Agents
- Princeton NLP 2026 — Single-Agent vs Multi-Agent benchmark comparison
- Microsoft AutoGen 2026 — Self-Adaptive LLM Agent Systems
- Token Budget Contracts (PyPI) — Confidence-gated spending
