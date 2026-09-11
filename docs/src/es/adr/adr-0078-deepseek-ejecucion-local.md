# ADR 0078: DeepSeek + deepseek-harness — Ejecución Local Real

## Estado
Aplicado | `harness/model_router/local_executor.py` + `TokenUsageTracker.pressure` + `harness/memory_rag/compaction_pipeline.py` + WFP/R1 en principios | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Auditoría 2026-09-08 + `01_search_frontier/deepseek-harness-master` (monorepo TS: packages core/llm/compaction/subagent, prefix-cache DeepSeek, benchmarks por user-path) + papers DeepSeek V3/R1 (MLA, MTP/speculative, FP8, GRPO, R1-distill, R1 verification+reflection):

1. **Gap crítico (propio)**: la DECISIÓN trivial→local era correcta (10/10 simulación, `run.py:420` vivo, Ollama con 8 modelos) pero `OllamaClient.generate/chat` **no tenía callers productivos** — el modelo externo hacía el trabajo y el routing era telemetría. Triviales pagaban cloud.
2. **deepseek-harness** (ideas transferibles): token-meter determinista (pressure sin LLM), compactación 2 fases (prune tool-results → summarize), disciplina prefix-cache (system frozen, historia append-only), `reasoningEffort` por ruta, archivos como handles (ya cubierto por artifact_store ADR-0074).
3. **DeepSeek V3/R1**: MTP/speculative (ya cubierto por speculative_decoder), R1 verify+reflect destilable, long-CoT con control de longitud, R1-Distill pequeños para tier local (deepseek-r1:8b ya instalado), GRPO sin critic (idea para voting con reward reglado — futuro), MLA/KV como atributo de selección (futuro, sin serving propio).

## Decisión
1. **`LocalExecutor`**: ejecuta tareas cerradas (allowlist: resumir/formatear/extraer/traducir/contar/convertir/listar/renombrar) en el tier local con fallback a cloud ante cualquier fallo (Ollama caído, tier None/frontier-only, excepción) — nunca lanza; métricas `local_tasks`/`cloud_tasks`. Triviales = 0 tokens cloud.
2. **`TokenUsageTracker.pressure(budget)`**: ratio usado/presupuesto determinista para decidir prune/summarize/evict antes del overflow.
3. **`prune_then_summarize`**: fase 1 evicta tool-lines >500 chars a artifacts (force), fase 2 `structured_compact`; preview truncado a 200 chars/línea (fix: previews de 1 línea gigante).
4. **WFP/R1 en principios**: `reason→verify→reflect→final` con verdict explícito y early-stop.

TDD: 14 tests nuevos; ruff 0; mutante del gate muerto.

## Consecuencias
### Positivas
- El loop local se cierra: decisión + ejecución en el mismo tier.
- Presión medible sin LLM; pipeline de compaction en el orden correcto.
- R1 como disciplina de razonamiento sin costo de tokens extra.

### Negativas
- `LocalExecutor` aún no está enchufado en `run.py` (siguiente paso: llamar tras `_apply_model_routing` cuando source==local).
- GRPO-voting y kv_efficiency quedan como trabajo futuro documentado.

## Alternatives Considered
1. **Dejar el routing como telemetría**: contradice TKN (triviales pagando cloud).
2. **Ejecutar TODO lo local en Ollama**: tareas abiertas necesitan tools/cloud; la allowlist es el compromiso seguro.
3. **Entrenar/fine-tunear**: fuera del alcance (somos consumidores de modelos).

## Relacionado
- ADR-0068 (cascada), ADR-0069 (Ollama tiers), ADR-0074 (artifacts), ADR-0076 (boundary)
- DeepSeek-V3 (arXiv:2412.19437), DeepSeek-R1, deepseek-harness-master (TS)
