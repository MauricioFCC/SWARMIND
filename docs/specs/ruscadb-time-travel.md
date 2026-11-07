# Spec — Time Travel (execute_at) en SWARMIND

> Estado: proposed — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `time_travel.md`, `time_travel_real.md`.

## 1. Objetivo
Permitir reproducibilidad de retrieval en un punto del tiempo (LSN) usando
`execute_at` de RuscaDB.

## 2. Diseno
- `RuscaDBStore.execute_at(sql, lsn)` expone `execute_at`.
- El binding FFI necesita `ruscadb_execute_at` (nuevo).
- Usar para: auditoria, debugging, replay de queries.

## 3. Integracion
- Agregar `ruscadb_execute_at` al C-ABI.
- `RuscaDBStore.execute_at(sql, snapshot_lsn)`.
- `GraphRAGRetriever` opcionalmente usa snapshot para reproducibilidad.

## 4. Outcome medible
- Reproducibilidad: misma query + mismo LSN → mismos resultados.
- Latencia p95 < 50ms.

## 5. Esfuerzo: 3 dias (FFI) + 2 dias (integracion).
