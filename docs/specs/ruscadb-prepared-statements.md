# Spec — Prepared Statements en SWARMIND

> Estado: proposed — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `prepared_statements.md`, `prepared_statements_real.md`.

## 1. Objetivo
Evitar re-parseo de RQL en queries repetidas usando prepared statements
de RuscaDB.

## 2. Diseno
- `RuscaDBStore.prepare(sql)` devuelve un handle de statement.
- `execute_prepared(handle, params)` ejecuta con parametros.
- Cache de statements por SQL hash.

## 3. Integracion
- `RuscaDBStore.execute()` usa prepared statements internamente.
- `hybrid_search`, `full_text_search` usan prepared statements.

## 4. Outcome medible
- Latencia de query repetida reducida en >= 30%.
- 0 re-parseo en hot path.

## 5. Esfuerzo: 2 dias (FFI) + 1 dia (integracion).
