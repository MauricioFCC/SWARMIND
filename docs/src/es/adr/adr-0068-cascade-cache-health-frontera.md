# ADR 0068: Cascada STEER-lite + Salud de Cache (Frontera tokens 2026)

## Estado
Aplicado | `harness/model_router/cascade_router.py` + `TokenUsageTracker.cache_health` | Propietario: @coordinator | Fecha: 2026-09-06

## Contexto
Research frontera final (sep-2026, 2 tracks):
- **Tokens**: routing 40-60% (distribucion 70/20/10 = -60-80%), caching -90% input con hit>60% (ProjectDiscovery 7%→84% = -59-70% spend), batch API -50%, cascada STEER (intenta small, escala si confianza<τ), cache-busters (timestamps, few-shots reordenados, tool lists dinamicas) como causa #1 de hit bajo.
- **Local**: Ollama/MLX + Qwen3 7-14B 4-bit, SLMs 270M-3.8B con tool-calling, regla 70-80% queries no necesitan frontera (50-100x en path local), speculative decoding 2-3x solo en concurrencia baja-media, PagedAttention -90% waste KV.

SWARMIND ya tenia: `ComplexityRouter` (decide una vez, sin cascada), `TokenUsageTracker` con `cache_hit_ratio` pero sin flag de bug estructural, delegacion Ollama 4-tier, `speculative_decoder.py`, `prompt_cache_builder.py`. Deltas implementados (TDD, IDP: sin duplicar):

## Decisión
1. **`CascadeRouter`** (`harness/model_router/cascade_router.py`): ejecuta el tier decidido y escala small→frontier si confianza < 0.7 (gate estricto, boundary testeado). `force_tier` como escape_hatch. Cada intento loguea (route, confidence, cost_usd) con tabla calibrable (small $0.25/$1.25, frontier $5/$25 por MTok) para calibrar thresholds offline.
2. **`CacheHealth`** (`TokenUsageTracker.cache_health`): hit_ratio + `needs_attention` cuando volumen ≥10K y ratio <0.60, con reason que nombra sospechosos (cache-busters).
3. **Personal**: auditado — `scripts/deploy_local.json` gitignored (.gitignore:151), scripts con paths de autor ya ignorados (líneas 17-31) y portables vía `Path.home()`/env vars; 0 secretos y 0 `C:\Users\USUARIO` hardcodeados en `harness/`.

## Consecuencias
### Positivas
- Cascada sin router entrenado: paga small por defecto, frontier solo con duda.
- Bug estructural de cache detectable por metrica, no por intuicion.
- Mutantes M-gate y M3-preview verificados muertos (kill real, no harness).

### Negativas
- Precios default son aproximados (requieren calibracion con spend real).
- Sin batch API para evals no-urgentes (diferido: -50% potencial).

## Alternatives Considered
1. **Solo ComplexityRouter**: decide una vez; sin segunda oportunidad ante duda.
2. **Mutmut global**: el stage propio da falsos negativos en modulos con imports (documentado); mutacion manual dirigida es honesta y barata.
3. **Batch API ya**: alto valor pero superficie nueva (provider batch endpoints); diferido a ADR futuro.

## Relacionado
- ADR 0013 (token economics), ADR 0050 (capa semantica), ADR 0066 (prompt-cache TTL), ADR 0038 (Ollama 4-tier en roadmap)
- tokenoptimize.dev 2026-06-14, digitalapplied prompt-caching 2026-06-16, traversaal speculative-decoding 2026-08-25
