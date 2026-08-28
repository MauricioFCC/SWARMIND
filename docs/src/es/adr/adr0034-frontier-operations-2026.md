# ADR-0034: Frontier Operations — Golden Signals, Cache Geometry, Dreaming, SLM-First, LAMaS y Speculative Tool Execution

## Estado
**ACEPTADO** — Mesa de trabajo (retrospectivo + investigación web especializada 2026) + implementación completa. Julio 2026.

## Contexto

Análisis retrospectivo de velocidad y token economics identificó que SWARMIND ya implementa el stack Token Economics más completo de la industria (-38% tokens CacheShape, -41% costo Structured Compaction, -44% tiempo Scoped Context, WAL + Failure-Spend Governance, Observation Masking -60%, Structured Output -40%). Sin embargo, la investigación web especializada de vanguardia 2026 (15+ fuentes: Zylos, MorphLLM, SJTU/MSR arXiv 2603.18897, UCF arXiv 2601.10560, RouteLLM UC Berkeley, Anthropic Dreaming, SRE Golden Signals, Algolia, AgentMarketCap) reveló **6 brechas accionables** que este ADR cierra:

| # | Brecha | Evidencia 2026 | Impacto potencial |
|---|--------|----------------|-------------------|
| 1 | Sin Golden Signals LLM (p50/p95/p99, TTFT, cache-read, cost/task) | SRE 2026: "el promedio esconde el tail; p95/p99 es lo que rompe SLAs" | Gobierno real del gasto y latencia |
| 2 | Sin Cache Geometry Discipline (orden estático→dinámico) | Zylos/Redis: "cache geometry — dónde se coloca el contenido estático vs dinámico determina el hit rate" (87.4% vs 10-20%) | -90% input cost en prefijos largos |
| 3 | Sin consolidación de memoria (Dreaming) | Anthropic May 2026: dedup + stale removal + compactación async | Memoria viva, calidad que mejora con semanas |
| 4 | Sin routing SLM-first | RouteLLM (UC Berkeley): 95% calidad con -85% costo | -70-85% costo en 60-80% del tráfico |
| 5 | Sin orquestación latency-aware | LAMaS (UCF arXiv 2601.10560): -38-46% critical path | Menor latencia end-to-end |
| 6 | Sin speculative tool execution | PASTE (SJTU/MSR arXiv 2603.18897): -43.5% latencia avg, -55.4% p99 | Mayor velocidad percibida |

**Principio rector**: "El bottleneck de 2026 no es el modelo — es el plumbing" (Zylos). La frontera del performance en agentes se movió de la capacidad del modelo a la ingeniería de sistemas. SWARMIND debe gobernar lo que mide (Golden Signals), explotar la geometría del cache, consolidar memoria, y ejecutar en paralelo especulativo donde sea seguro.

## Decisiones e Implementación

### 1. Golden Signals LLM — `harness/orchestrator/golden_signals.py` (ROI: P0)

**Problema**: `telemetry.py` mide `duration_ms` promedio pero no percentiles, TTFT, cache-read tokens ni cost-per-task. La industria 2026 gobierna sistemas por p50/p95/p99 y costo por tarea completada.

**Decisión**: Nuevo módulo `GoldenSignals` que recolecta y agrega métricas SRE-flavored para agentes LLM:

- **Latencia**: p50, p95, p99 por nivel y por sesión (nunca promedio solo).
- **TTFT** (time-to-first-token): latencia percibida de primera respuesta.
- **Cache-read tokens**: % de input tokens servidos desde cache del provider (detección de cache invalidator silencioso si es 0 en requests repetidas).
- **Cost per task**: tokens input×tarifa + tokens output×tarifa (5x peso output) + cache-read×10% tarifa.
- **Failure-spend ratio**: tokens gastados en fallos / tokens totales.
- **Throughput**: tokens/seg bajo concurrencia.

**API pública**:
```python
class GoldenSignals:
    def record_request(self, *, latency_ms, ttft_ms, input_tokens, output_tokens,
                       cache_read_tokens=0, cost_input_per_1k=0.0, cost_output_per_1k=0.0,
                       status="success", level=0, agent="") -> None
    def percentiles(self, key="latency_ms") -> dict  # p50/p95/p99/max/mean
    def cost_per_task(self) -> float
    def cache_hit_rate(self) -> float              # cache_read / input
    def failure_spend_ratio(self) -> float
    def snapshot(self) -> dict                      # export JSON-ready
```

**Cálculo de percentiles**: método del "nearest rank" (ordenar + índice `ceil(p/100 * n)`) — determinista, sin dependencias, testeable.

**Integración**: Composition Root — `TaskOrchestrator.enable_golden_signals()` inyecta el tracker; `TelemetryTracker` puede delegar en él en `finalize_session`.

**Referencias**: SRE Golden Signals (Google), Algolia AI evaluation, QASkills 2026, AgentPatterns.

### 2. Cache Geometry Discipline — `harness/memory_rag/cache_geometry.py` (ROI: P0)

**Problema**: El contenido estático (system prompts, skills, instrucciones) se intercala con contenido dinámico, rompiendo el prefix-cache del provider. Resultado: cache-read tokens ≈ 0 en requests repetidas.

**Decisión**: Reordenador de prompt que separa **bloques estáticos** (con hash estable) al inicio y **bloques dinámicos** al final, maximizando la reutilización del prefijo. Incluye **medición** de la geometría:

- `CacheGeometry.reorder(blocks)` → prompt reordenado [estáticos..., dinámicos...] preservando contenido.
- `CacheGeometry.classify(text)` → "static" | "dynamic" (heurística: marcadores `{{...}}`, timestamps, UUIDs, fechas → dinámico; instrucciones/skills/constantes → estático).
- `CacheGeometry.static_prefix_hash()` → hash SHA-256 del prefijo estático (detecta invalidación silenciosa).
- `CacheGeometry.report(requests)` → cache-read %, cambios de hash de prefijo entre requests.

**Regla de oro**: contenido que no cambia entre llamadas va al inicio; contenido que cambia (contexto de tarea, timestamps) va al final. El prefijo estático debe ser **idéntico byte a byte** entre llamadas consecutivas.

**Integración**: `ContextAssembler` y `prompt_cache_builder.py` usan `CacheGeometry.reorder` antes de ensamblar el prompt final.

**Referencias**: Zylos Research 2026 (cache geometry), Redis LangCache (73% reducción), llm-d (87.4% hit rate con geometría bien estructurada vs 10-20% con contenido variable temprano).

### 3. Dreaming-lite — `harness/memory_rag/dreaming.py` (ROI: P1)

**Problema**: La memoria federada (`knowledge/`, `sessions/`) acumula ruido, duplicados y entradas obsoletas. Anthropic demostró (May 2026) que los agentes long-running degradan sin consolidación — "memory rot".

**Decisión**: Consolidación asíncrona de memoria inspirada en Anthropic Dreaming, fuera del path de latencia:

- **Deduplicación**: entradas con similitud de Jaccard > umbral se fusionan (conservando la más reciente y más densa).
- **Stale removal**: entradas no referenciadas y con edad > `max_age_days` se eliminan (configurable).
- **Compacción**: entradas restantes se re-frasean por densidad (resumen 1 línea con metadatos clave conservados).
- **Inmutabilidad**: la consolidación escribe un NUEVO store consolidado; el original no se altera (patrón copy-on-write de Anthropic Dreams API).
- **Idempotencia**: `consolidate()` es puro y determinista dado el mismo input.

**API pública**:
```python
class DreamingConsolidator:
    def __init__(self, *, similarity_threshold=0.85, max_age_days=90,
                 min_density_chars=40) -> None
    def consolidate(self, entries: list[dict]) -> ConsolidationResult
    def consolidate_dir(self, source: Path, dest: Path | None = None) -> ConsolidationResult
```

**Integración**: `sync_hermes.py --dream` invoca la consolidación sobre `sessions/` → escribe en `knowledge/Swarmind_bridge/`. También disponible como script standalone `harness/scripts/dreaming_consolidate.py`.

**Referencias**: Anthropic Dreaming (Code with Claude, May 2026), OpenClaw Dreaming, agent-memory.bruegs.com.

### 4. SLM-First Workers — `harness/orchestrator/slm_router.py` (ROI: P1)

**Problema**: Todo el tráfico usa el mismo modelo, pagando precio frontier por tareas mecánicas (extracción, clasificación, formateo JSON, validación de schema) que un SLM resuelve al 95-99% de calidad (RouteLLM, Berkeley Function Calling Leaderboard v2).

**Decisión**: Router de ejecución con **escalación por confianza** (confidence-gated escalation):

- `SlmRouter.route(task)` → `SLM` | `FRONTIER` basado en: complejidad (DifficultyRouter), tipo de tarea (whitelist SLM-friendly: extraction, classification, formatting, schema validation, summarization), y presupuesto (token_budgets.yaml).
- `SlmRouter.execute(...)` → si se eligió SLM pero la confianza del resultado es < umbral, **escala** esa única llamada a FRONTIER (patrón "local-first, escalate-on-trouble" de NVIDIA 2026).
- **Determinista**: mismas entradas → misma decisión (temperature=0, sin random).
- **Métricas**: % tráfico en SLM, % escalado, costo estimado ahorrado.
- **Extensible**: el backend SLM es un callable inyectable (por defecto un stub local con API OpenAI-compatible para Phi-4-mini / Qwen3.6-27B cuantizado en RTX 4060 8GB).

**API pública**:
```python
class SlmRouter:
    def __init__(self, *, slm_backend=None, frontier_backend=None,
                 confidence_threshold=0.85, slm_friendly_agents=frozenset({...}))
    def decide(self, task_type: str, difficulty: int) -> str      # "slm" | "frontier"
    def execute(self, task_type, difficulty, payload, check_confidence=...)
    def stats(self) -> dict
```

**Integración**: `AgentSelector`/`DifficultyRouter` consultan `SlmRouter.decide()` para enrutar subtareas de ejecución; el orquestador conserva FRONTIER para planning y síntesis.

**Referencias**: RouteLLM (UC Berkeley), SLM-first routing (NVIDIA, AgentMarketCap, Digital Applied), "Large model planning + SLM execution" (QubitTool: 72% reducción).

### 5. LAMaS-lite — Latency-Aware Orchestration `harness/orchestrator/latency_aware.py` (ROI: P2)

**Problema**: El DAG de `TaskPlanner.get_levels()` agrupa por profundidad topológica, no por **ruta crítica**. LAMaS (UCF 2026) demostró que optimizar explícitamente la latencia del critical path reduce 38-46% el tiempo end-to-end.

**Decisión**: Analizador de ruta crítica sobre el plan:

- `CriticalPath.compute(plan)` → lista de subtasks en la ruta crítica (camino más largo en el DAG ponderado por `estimated_latency_ms` o 1.0 por defecto).
- `CriticalPath.longest_path(plan)` → longitud total estimada + subtasks críticos.
- `CriticalPath.optimize(plan)` → reordena niveles para ejecutar primero los predecesores de la ruta crítica (sin romper dependencias): los nodos críticos se priorizan dentro de su nivel.
- `CriticalPath.parallelizable_pairs(plan)` → pares de subtasks independientes que pueden ejecutarse en paralelo (información para el scheduler).

**Propiedad clave**: `optimize()` preserva el orden topológico y nunca invalida dependencias — es una heurística determinista de priorización.

**Integración**: `TaskPlan.get_levels()` consulta `CriticalPath` para ordenar dentro de cada nivel; el scheduler (TaskOrchestrator) lanza primero los críticos.

**Referencias**: LAMaS (Shi, Zheng, Lou — UCF, arXiv 2601.10560), PASTE scheduling, "Audit Agent Dependencies" (2026 Guide to MAS).

### 6. Speculative Tool Execution — `harness/orchestrator/speculative_tool_exec.py` (ROI: P2)

**Problema**: El loop agente "think → call tool → wait → think" expone la latencia de herramientas en la ruta crítica (35-61% del tiempo total, según Zylos). PASTE (SJTU/MSR) demostró -43.5% latencia con ejecución especulativa de tools.

**Decisión**: Middleware de ejecución especulativa con **seguridad de lado-efectos**:

- `SpeculativeToolExecutor` mina patrones de tool-calls desde el AgentBus/ejecuciones previas (patrón: contexto → siguiente tool con probabilidad empírica).
- **Solo tools side-effect-free** (lecturas, búsquedas, consultas) son elegibles para especulación — escrituras/API mutantes NUNCA (policy-driven, como PASTE).
- Los resultados especulativos se **aislan** hasta que el LLM confirma la tool; si la predicción es errónea, se descartan sin consecuencias (lossless).
- `PatternLearner`: aprende pares (tool_actual, tool_siguiente, frecuencia) de trayectorias reales.
- `SpeculativeToolExecutor.predict(context) → list[(tool, params, prob)]` top-k.
- `SpeculativeToolExecutor.execute_speculative(context)` → ejecuta en paralelo las predicciones elegibles y las guarda en cache provisional.
- **Métricas**: hit rate, tiempo ahorrado estimado, % ejecuciones especuladas.

**API pública**:
```python
class PatternLearner:
    def observe(self, tool_name: str, next_tool: str | None) -> None
    def predict(self, current_tool: str, k: int = 3) -> list[tuple[str, float]]
class SpeculativeToolExecutor:
    def __init__(self, *, learner=None, eligible=None, dry_run=False)
    def predict(self, current_tool) -> list[tuple[str, float]]
    def run_speculative(self, current_tool, executor) -> dict[str, object]
    def confirm(self, tool: str, params) -> object | None
    def stats(self) -> dict
```

**Seguridad**: default `eligible=frozenset()` (NADA es especulable sin registro explícito); `dry_run=True` por defecto (solo mide, no ejecuta). Prohibidos por policy: `write`, `delete`, `update`, `execute`, `send`, `deploy`.

**Integración**: `AgentBus` / `MCPToolExecutor` pueden envolverse con `SpeculativeToolExecutor` como middleware (sin modificar la lógica del agente, como PASTE).

**Referencias**: PASTE (Sui et al., arXiv 2603.18897), Speculative Actions (Ye et al., 2510.04371), Zylos speculative execution research.

## Arquitectura

```
harness/
├── orchestrator/
│   ├── golden_signals.py        # Idea 1 — Golden Signals LLM
│   ├── slm_router.py            # Idea 4 — SLM-first routing con escalación
│   ├── latency_aware.py         # Idea 5 — Critical path analysis (LAMaS-lite)
│   └── speculative_tool_exec.py # Idea 6 — Speculative tool execution (PASTE-lite)
├── memory_rag/
│   ├── cache_geometry.py        # Idea 2 — Cache Geometry Discipline
│   └── dreaming.py              # Idea 3 — Dreaming consolidation async
└── scripts/
    └── dreaming_consolidate.py  # CLI para Dreaming-lite (integra sync_hermes --dream)
```

**Principios aplicados**: Single Responsibility (un módulo = una idea), Composition Root (integración por inyección, sin acoplar), Idempotencia (ADR-0006), DRY (reutiliza DifficultyRouter, token_budgets.yaml, AgentBus), DocStrings ES-UTF8 + errores WHAT+WHY+WHERE (ADR-0007), TDD-as-SSOT (ADR-0033: specs primero, código después).

## Tests

Cada módulo incluye suite de tests unitarios:

| Módulo | Archivo tests | Casos clave |
|--------|---------------|-------------|
| golden_signals | `test_golden_signals.py` | percentiles p50/p95/p99, cost/task con tarifas, cache hit rate, failure-spend ratio, snapshot |
| cache_geometry | `test_cache_geometry.py` | clasificación static/dynamic, reorder preserva contenido, hash estable, detección invalidación |
| dreaming | `test_dreaming.py` | dedup por Jaccard, stale removal, compactación por densidad, copy-on-write, idempotencia |
| slm_router | `test_slm_router.py` | decisión determinista, whitelist, escalación por confianza, stats, fallback |
| latency_aware | `test_latency_aware.py` | longest path, critical path correcto, optimize preserva topología, parallel pairs |
| speculative_tool_exec | `test_speculative_tool_exec.py` | learner aprende patrones, predict top-k, dry_run no ejecuta, políticas de seguridad, confirm lossless |

## Consecuencias

### Positivas
- **Gobierno real del gasto**: cost-per-task y cache-read tokens permiten probar cada optimización en dólares (Hedge Fund doctrine).
- **Cache explotado**: la geometría del prompt maximiza el prefix-cache del provider (potencial -90% input en prefijos largos).
- **Memoria viva**: Dreaming-lite convierte `knowledge/` (hoy vacío) en un store consolidado y consultable.
- **Costo estructural**: SLM-first en 60-80% del tráfico → -70-85% costo sin degradar calidad (escalación por confianza).
- **Velocidad**: critical path optimizado (-38-46%) + ejecución especulativa segura (-43% latencia documentada por PASTE).
- **Seguridad**: la especulación de tools es opt-in y prohibida para side-effects; dry_run por defecto.

### Negativas
- Los percentiles requieren suficiente volumen de muestras para ser significativos (n≥5 recomendado).
- Cache Geometry asume que el provider usa prefix-caching (Anthropic/OpenAI sí; algunos no).
- SLM routing requiere un backend SLM real para materializar el ahorro (stub incluido; Phi-4-mini Q4 ~3GB en RTX 4060).
- Dreaming-lite es heurístico: la deduplicación por Jaccard puede fusionar entradas falsamente similares (mitigado por umbral configurable 0.85).
- La ejecución especulativa añade complejidad de trazado (¿el resultado vino de cache especulativo o de ejecución real?).

### Pendiente
- Conectar `GoldenSignals` al dashboard JSON de `TelemetryTracker.export_summary()`.
- Materializar el backend SLM real (Phi-4-mini / Qwen3.6-27B cuantizado) en `slm_router.py`.
- Integrar `SpeculativeToolExecutor` como middleware en `MCPToolExecutor` (hoy queda como librería testeada + dry-run).
- Alimentar `PatternLearner` con trayectorias reales del `AgentBus` en producción.

## Referencias
- **SRE Golden Signals** (Google) — p50/p95/p99, throughput, errores, saturación.
- **Algolia AI Evaluation** — cost per task como métrica subestimada; percentiles a nivel tarea.
- **Zylos Research (2026-04-03)** — KV cache reuse, cache geometry, KVFlow, especulación multi-nivel.
- **Redis LangCache** — hasta 73% reducción en workloads de alta repetición.
- **Anthropic Dreaming (May 2026)** — consolidación async, dedup + stale + compact, copy-on-write, immutabilidad.
- **RouteLLM (UC Berkeley)** — 95% calidad con -85% costo.
- **LAMaS (UCF, arXiv 2601.10560)** — latency-aware orchestration, -38-46% critical path.
- **PASTE (SJTU/MSR, arXiv 2603.18897)** — speculative tool execution, -43.5% avg / -55.4% p99.
- **Speculative Actions (Ye et al., 2510.04371)** — framework lossless de especulación.
- **NVIDIA SLM-Agents (arXiv 2506.02153)** — SLMs como futuro del agentic AI.
- **J.Servo 2026** — orden de optimización: Audit → Instrument → Compress → Cache → Route → Cap.
