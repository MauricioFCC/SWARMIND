# Spec — Query Result Cache en SWARMIND

> Estado: **implementado** (ciclo 11.99, 2026-11-16) — Dueño: harness/memory_rag — Frontera: 2026-10.
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

## 6. Estado de implementacion (ciclo 11.99)

Lo implementado es el **L1 in-memory** (`QueryResultCache`, TTL 300 s); la
delegacion al semantic cache persistente sigue siendo una capa separada
(`semantic_cache_get/set`).

- **Cableado real**: `search()` y `full_text_search()` leen via
  `_cached_rows()`, que propaga `RuscadbError` para conservar la degradacion
  `[]` de cada llamador. Antes `cached_execute()` tenia 0 llamadas de
  produccion.
- **Clave**: `sha256(sql + repr(params))`. Las rutas cacheadas no usan
  `params` (el SQL ya lleva el vector/texto embebido como literal escapado).
- **Invalidacion**: `insert`, `update_records` (cubre `record_access`),
  `delete`, `attach_blob` y `delete_collection` invalidan la coleccion. Antes
  `update_records` no invalidaba: un hit podia servir metadata vieja.
- **Observabilidad**: `query_cache_stats()` expone `entries`, `collections`,
  `hits`, `misses`, `expired` (`expired` es subconjunto de `misses`).
- **Tests**: `harness/tests/test_query_cache.py` (hit, miss, TTL, invalidacion)
  y `test_ruscadb_store.py::test_search_usa_cache_e_invalida_al_actualizar`.

No implementado y por que:
- **Persistencia del L1**: el requisito es evitar re-ejecucion en proceso; un
  cache en disco anade invalidacion entre procesos que nadie consume aun.
- **`params` en las rutas cacheadas**: el SQL se construye con literales
  escapados; agregar parametros exigiria cambiar la firma de `search`.

El objetivo de hit rate >= 60% no se declara alcanzado: depende del workload.
