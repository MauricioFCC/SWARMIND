# Spec — Semantic Cache Persistente (RuscaDB) en SWARMIND

> Estado: implemented (ciclo 11.53) — Dueño: harness/memory_rag — Frontera: 2026-10.
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

## 6. Evidencia (ciclo 11.53)

- `RuscaDBStore.semantic_cache_set/get/delete/entries/purge_expired/metrics`.
- `SemanticCache` usa la API persistente para el hit exacto y delega la
  purga; ya no accede a `_lancedb_available`/`_db`/`_mem_collections`.
- Tests: `harness/tests/test_semantic_cache_persistent.py` (5 passed),
  `test_trust_aware_retrieval.py` (roundtrip/TTL/metrics).
