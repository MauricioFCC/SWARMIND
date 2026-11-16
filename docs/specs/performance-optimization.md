# Spec — Optimizacion de Rendimiento (GPU, async, batching, caching)

> Estado: **implementado parcial** (ciclo 11.99, 2026-11-16) — Dueño: harness/parallel + harness/observability — Frontera: 2026-10.
> Referencias: CUDA graph capture, async I/O, batching, LRU-K, memory pools.

## 0. Estado de implementacion (evidencia)

| Item | Estado | Evidencia / motivo |
|---|---|---|
| L1 in-memory TTL (§5) | implementado 11.99 | `QueryResultCache` cableada en `search()`/`full_text_search()`; contadores `hits/misses/expired` en `stats()` |
| Invalidacion por version de datos (§5) | implementado 11.99 | `insert`, `update_records`, `delete`, `attach_blob`, `delete_collection` invalidan su coleccion |
| p50/p95/p99 por operacion (§7) | implementado 11.99 | `harness/observability/latency.py::LatencyWindow` + `RuscaDBStore.latency_stats()` para `insert`/`search`/`full_text_search` |
| Buffer pool LRU-K (§6) | implementado | pool configurable (default 64 marcos, ciclo 11.98) |
| Batching (§4) | descartado | medicion 11.98: `insert_many` en lote rinde **0.93x** (peor) frente a inserts individuales por el coste de commit del motor |
| L2 semantic cache (§5) | implementado | `semantic_cache_get/set` persistente |
| CUDA / async I/O (§2, §3) | pendiente | requiere GPU y drivers fuera del entorno de gates; sin medicion no se declara |

Objetivo de hit rate (>= 60%) queda como metrica a observar con
`store.query_cache_stats()` en workloads reales; no se afirma alcanzado.

## 1. Objetivo

Maximizar throughput y minimizar latencia en SWARMIND: uso eficiente de GPU
(CUDA), I/O asincrono, batching de operaciones, pools de memoria, y caching
multi-nivel.

## 2. GPU / CUDA

- Kernel fusion para embeddings (model2vec-rs, SPEC-0083).
- Batch inference: acumular N requests antes de inferir.
- Pin memory + async H2D/D2H transfers.
- Multi-GPU: data parallelism para embeddings masivos.
- Profiling con nvidia-smi / torch profiler.

## 3. I/O asincrono

- Async file I/O para WAL writes (aiofiles).
- Async HTTP para LLM calls (httpx/aiohttp).
- Connection pooling para MCP servers.
- Backpressure: limitar concurrencia de fan-out.

## 4. Batching

- `insert_many` (RuscaDB): N registros, un commit (ya disponible).
- Batch embeddings: procesar N textos por forward pass.
- Batch RQL: ejecutar multiples queries en una transaccion.

## 5. Caching multi-nivel

- L1: in-memory (LRU, TTL).
- L2: RuscaDB semantic cache (persistente).
- L3: disco (modelos, embeddings precomputados).
- Cache invalidation por version de datos.

## 6. Pools de memoria

- Buffer pool LRU-K (RuscaDB, ya implementado).
- Tensor pool para reutilizar buffers de embeddings.
- Connection pool para DB/MCP.

## 7. Medición

- Latencia p50/p95/p99 por operacion.
- Throughput (ops/s, tokens/s).
- VRAM usage (nvidia-smi).
- Cache hit rate.

## 8. Outcome medible

- Latencia de insert p95 < 10ms (batch 100).
- Throughput de embeddings >= 1000 docs/s (GPU).
- Cache hit rate >= 60%.

## 9. Esfuerzo estimado

- Fase 1 (batching + pools): 2 dias.
- Fase 2 (async I/O): 3 dias.
- Fase 3 (GPU optimization): 1 semana.
- Fase 4 (caching multi-nivel): 2 dias.
