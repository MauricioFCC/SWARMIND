# Spec — Optimizacion de Rendimiento (GPU, async, batching, caching)

> Estado: proposed — Dueño: harness/parallel + harness/observability — Frontera: 2026-10.
> Referencias: CUDA graph capture, async I/O, batching, LRU-K, memory pools.

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
