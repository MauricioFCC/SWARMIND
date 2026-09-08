# ADR 0074: Optimización de Contexto Frontera — Artifacts, Cue-Ledger, Compaction Calibrada y Eficiencia por Modelo

## Estado
Aplicado | `harness/memory_rag/{artifact_store,cue_ledger,compaction_calibration}.py` + `TokenUsageTracker.model_efficiency_report` | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Pregunta del usuario: ¿qué más se puede optimizar/expulinar (expulsar waste) en SWARMIND? Audito el estado actual (todo lo ya aplicado: prompt caching, compaction, semantic cache, routing triple, batch_vote, observation masking, reanchor, llm_grep, local 5-tier) y research frontera 2026 con 11 técnicas destiladas. Priorizo las 4 de mayor ROI implementables sin deps externas:

1. **Artifact-backed eviction (tier 1)**: tool result grande → disco; al contexto va {preview + handle + size}. El observation masking OCULTA sin acceso; la eviction CONSERVA acceso por handle/offset.
2. **Fire-ledger cue-anchored** (arXiv 2607.20972): ledger de hechos cortos + procedencia, dedup de inyecciones repetidas (hash), staleness por hash/mtime del source, reset en compaction. Medido en el paper: **−42% tokens, grep/find −54%, costo −30%**.
3. **Compaction calibrada** (AgeMem 2026): ceiling con zonas warn (0.75 → suave 0.7) / critical (0.90 → agresiva 0.4) + dedup de líneas repetidas; evita compaction prematura (pierde info) y tardía (overflow).
4. **Eficiencia por modelo** (Copilot harness 2026): el mismo harness varía hasta **40%** en tokens entre modelos; medir tokens/llamada por modelo permite re-ponderar routing por eficiencia real, no solo precio.

Diferidos con causa (YAGNI): FP8 KV cache (flags de serving local), MLA routing (no aplica aún), PTC sandbox (SBX grande), continuous batching (requiere serving), contract-based evolution (evolve loop, ADR futuro).

## Decisión
1. **`ArtifactStore`** (`harness/memory_rag/artifact_store.py`): `evict(content, force)` → threshold 4000 chars; preview 3 líneas + `handle` + chars; `retrieve(handle, offset)` 0-based; JSON `{handle, content, chars}`; errores WHAT+WHY+WHERE.
2. **`CueLedger`** (`harness/memory_rag/cue_ledger.py`): `register(cue, source)` + `render_index()` (cue+procedencia, 1 línea/cue) + `inject(session_id)` con dedup por hash (2ª inyección → `""`, `dedup_hits++`) + `stale_cues()` (hash mtime+size) + `reset()` post-compaction + `tokens_saved` (cue 12 tok vs full 120 tok). Clock inyectable.
3. **`compact_calibrated`** (`harness/memory_rag/compaction_calibration.py`): `CompactionPolicy` frozen con validación (warn<critical, ratios en rango); zonas: bajo warn → solo dedup (≤2 repetidas); warn → structured_compact 0.7; critical → 0.4. Frontera exacta testada con spy (mutante `<`/`<=` muerto).
4. **`model_efficiency_report()`** (tracker): `ModelEfficiencyEntry(model, calls, avg_total_tokens)` ordenado desc — para re-ponderar routing.

TDD: 25 tests nuevos (4 archivos) + tracker 44 → 69 verdes; ruff 0; vulture 0; mutante de frontera crítica verificado muerto.

## Consecuencias
### Positivas
- Tool results grandes dejan de comerse el contexto (acceso preservado por handle).
- Inyecciones repetidas (heurísticas, reglas, hechos) se cobran 1 vez por sesión.
- Compaction con umbrales justificados en vez de un budget_ratio fijo.
- Base de datos de eficiencia por modelo para calibrar routing con datos reales.

### Negativas
- ArtifactStore escribe a disco (tmp por defecto; configurable) — limpieza pendiente por GC/sesión.
- CueLedger requiere wiring en el pipeline del orquestador (no auto-enchufado aún).
- Dedup de líneas exactas solo detecta repetición literal (no semántica).

## Alternatives Considered
1. **Solo ampliar observation masking**: oculta sin acceso — el agente no puede recuperar el detalle.
2. **Reinyectar AGENTS.md completo en cada turno**: attention suppression (frontera) + cache-buster.
3. **jsonschema/llmlingua deps**: YAGNI hasta caso real; la validación mínima y el dedup literal cubren lo esencial.

## Relacionado
- ADR-0066 (prefix cache), ADR-0068 (cascada/cache-health), ADR-0070 (re-anchor), ADR-0073 (batch vote/affinity)
- arXiv 2607.20972 (fire-ledger), AgeMem 2026, Copilot Agentic Harness Benchmarks 2026
