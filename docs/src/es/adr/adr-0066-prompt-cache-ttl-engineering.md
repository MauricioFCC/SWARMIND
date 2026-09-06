# ADR 0066: Prompt-Cache TTL Engineering — Prefijo Estable + Sin Cambio de Modelo

## Estado
Propuesto | Extiende `harness/memory_rag/prompt_cache_builder.py` | Propietario: @coordinator | Fecha: 2026-09-06

## Contexto
Existe `harness/memory_rag/prompt_cache_builder.py` con cache-breakpoint explícito para Anthropic/OpenAI y `base_principles.md` TKN (prompt caching, cache-shape -38%). El dump frontera (`RandomSearch.md` § prompt caching) aporta la capa operativa que falta:

1. **TTL**: conversación principal con suscripción ~1h; API key/provider y subagentes/workflows/compaction ~5 min. **El reloj arranca cuando inicia el request, no cuando termina** (respuesta 4 min → queda 1 min).
2. **Reutilización = prefijo**: el cache reutiliza el KV-state del prefijo y procesa SOLO LO NUEVO (respuesta idéntica + más rápida + ~75% menos en lecturas con Fable 5.1 a 0.025x).
3. **Lo que rompe el cache**: cambiar de modelo mid-conversación (KV inalcanzable), reenviar historial gigante sin compaction, prompts largos no estables.
4. Técnicas vigentes ya citadas: subagentes, skills progressive disclosure, compaction — todas para ventana limpia; falta **disciplina de cache**.

## Decisión
Endurecer `prompt_cache_builder.py` con 4 reglas medibles:

1. **Prefijo estable**: system + skills esenciales + budget primero, breakpoints fijos; lo volátil (tool results) después del breakpoint.
2. **Prohibido cambio de modelo mid-sesión** (router fija modelo por sesión; si cambia, advierte `CacheInvalidatedError`).
3. **TTL-aware**: `time_to_live_s` por superficie (chat 3600, API/subagente 300); `is_fresh()` gatea reutilización; `Effective-Input-Price = inp*miss_ratio*price + out*price` como métrica.
4. **Respuestas cortas + tareas en pasos** para no agotar la ventana TTL.

## Consecuencias
### Positivas
- Lecturas cache ~0.025x + latencia menor a igualdad de respuesta.
- Presupuesto atención (ADR-0053) + cache medibles juntos.

### Negativas
- Rigidez: prefijo estable limita reordenamientos ad-hoc.
- Requiere instrumentar `miss_ratio` real (hoy estimado).

## Alternatives Considered
1. **Solo compaction**: limpia ventana pero no abarata reenvíos (son ortogonales).
2. **Cache por defecto sin breakpoints**: hit-rate bajo, expiraciones silenciosas.
3. **Cambiar modelo libremente**: invalida KV, viola Cache-Shape.

## Relacionado
- ADR 0053 (presupuesto residencia), ADR 0013 (token economics), `prompt_cache_builder.py`, Fable 5.1
- `01_search_frontier/RandomSearch.md` § prompt caching + paper CLAUDE.md growth (76.8% reglas solo mueren por rewrite)
