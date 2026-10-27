# Spec — RQL Avanzado en SWARMIND

> Estado: proposed — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `rql_cte.md`, `rql_subqueries.md`, `rql_window_functions.md`,
> `rql_set_operations.md`, `rql_expression_language.md`, `query_extensions.md`.

## 1. Objetivo
Aprovechar las capacidades avanzadas de RQL (CTE, subqueries, window functions,
set operations, expresiones) para consultas complejas de analitica.

## 2. Capacidades
- CTE (WITH): consultas recursivas para grafos.
- Subqueries: agregaciones anidadas.
- Window functions: ranking, moving avg.
- Set operations: UNION/INTERSECT/EXCEPT.
- Expression language: calculos en SELECT.

## 3. Integracion
- `RuscaDBStore.execute()` ya pasa RQL crudo; solo documentar patrones.
- Agregar helpers en `RuscaDBStore` para CTE y window functions.

## 4. Outcome medible
- Consultas complejas expresables en una sola RQL.
- Latencia p95 < 100ms.

## 5. Esfuerzo: 3 dias.
