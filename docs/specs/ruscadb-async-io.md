# Spec — Async I/O (RuscaDB) en SWARMIND

> Estado: implemented-parcial (ciclo 11.53: thread offload) — Dueño: harness/parallel — Frontera: 2026-10.
> RuscaDB spec: `async_io.md`.

## 1. Objetivo
Hacer las operaciones de memoria no bloqueantes usando async I/O de RuscaDB.

## 2. Diseno
- Wrapper async sobre `RuscaDBStore` (asyncio).
- Pool de conexiones para MCP/LLM.
- Backpressure en fan-out del orchestrator.

## 3. Integracion
- `AsyncRuscaDBStore` con metodos async.
- `AgentBus` usa async store.
- `HybridRetriever.retrieve` async.

## 4. Outcome medible
- Throughput de queries >= 1000/s (async).
- Latencia p95 < 20ms bajo carga.

## 5. Esfuerzo: 1 semana.

## 6. Evidencia (ciclo 11.53)

- `AsyncRuscaDBStore` (search, hybrid_search, insert, full_text_search,
  delete, execute, close, `async with`, `from_path`).
- `HybridRetriever.aretrieve` (Spec 3: retrieve async).
- PENDIENTE: actor de escritura unico con cola bounded y backpressure
  tipado (hoy `asyncio.to_thread` sobre el handle compartido).
- Tests: `harness/tests/test_async_ruscadb.py` (6 passed).
