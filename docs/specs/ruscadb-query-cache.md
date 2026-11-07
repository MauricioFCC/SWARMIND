# Spec — Query Result Cache en SWARMIND

> Estado: proposed — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `query_result_cache.md`, `semantic_cache.md`, `semantic_cache_persistence.md`.

## 1. Objetivo
Cachear resultados de RQL frecuentes en RuscaDB (cache persistente) para
evitar re-ejecucion.

## 2. Diseno
- Cache key: hash(sql + params).
- TTL configurable (default 5 min).
- Invalidacion por escritura (insert/update/delete invalida cache de la coleccion).
- Delegar al semantic cache persistente de RuscaDB (SPEC-0093).

## 3. Integracion
- `RuscaDBStore.execute()` consulta el cache antes de ejecutar.
- `RuscaDBStore.insert/update/delete` invalidan cache de la coleccion.

## 4. Outcome medible
- Cache hit rate >= 60% en workloads repetitivos.
- Latencia en hit < 5ms.

## 5. Esfuerzo: 2 dias.
