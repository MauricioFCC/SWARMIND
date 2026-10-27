# Spec — Semantic Cache Persistente (RuscaDB) en SWARMIND

> Estado: proposed — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `semantic_cache.md`, `semantic_cache_persistence.md`.

## 1. Objetivo
Delegar el semantic cache de SWARMIND al cache persistente de RuscaDB
(SPEC-0093) para persistencia entre sesiones.

## 2. Diseno
- RuscaDB mantiene cache en `<data>.cache.json`.
- SWARMIND `SemanticCache` usa RuscaDB como backend en vez de in-memory.
- Invalidacion por version de datos.

## 3. Integracion
- `SemanticCache` acepta `store: RuscaDBStore`.
- Metodos: `get`, `set`, `clear`, `metrics`.
- Fallback a in-memory si RuscaDB no disponible.

## 4. Outcome medible
- Cache hit rate >= 70% en sesiones repetidas.
- Persistencia entre reinicios de opencode.

## 5. Esfuerzo: 2 dias.
