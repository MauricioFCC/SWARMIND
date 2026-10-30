# Auditoría de implementación — 2026-10-29 (Ciclo 11.53)

> Cierra los pendientes de `audit-implementacion-2026-10-28.md` (11.52).
> Método: verificación contra código + tests ejecutados + gates deterministas.
> Severidad: 🔴 bloqueante, 🟡 sugerencia, ⚪ observación.

## 1. Resumen ejecutivo

- **7236 tests** recolectados (11.52: 7179).
- **Ruff 0**, **Vulture 0** (min-confidence 80).
- **`check_architecture.py --gate` → OK: 0 violaciones bloqueantes (F1, F2, F4)**.
- **2 ciclos de import reales corregidos** (`harness.qa ↔ detector/predictor`) y
  regla F4 refinada: los imports diferidos dentro de funciones no cuentan
  (técnica estándar para romper ciclos).
- **`harness/domain/ports.py` pasa de 0 a 2 consumidores de producción**
  (`vector_store_factory`, `hybrid_retriever`) + gate de conformance en CI.
- **`run_commands._create_store()` estaba roto** (importaba
  `harness.db.vector_store`, módulo inexistente): ahora usa la factory.

## 2. Tabla de specs (estado real tras el ciclo)

| Spec | Declarado | Evidencia | Veredicto |
|---|---|---|---|
| clean-architecture-hexagonal | implemented | `ports.py` (6 puertos) + `get_vector_store` + `LanceVectorStore.__new__` + ADR-0104 | ✅ IMPLEMENTADO |
| recursive-harness-optimization | implemented | `bounded_recursion.py`, `reflection_memory.py` | ✅ IMPLEMENTADO |
| memory-data-optimization | implemented | `RuscaDBStore` + `memory_parity` | ✅ IMPLEMENTADO |
| performance-optimization | partial | `static_embeddings` cacheado, `query_cache` cableado | 🟡 PARCIAL |
| ruscadb-full-potential | implemented | C-ABI 29 funciones, store 60+ métodos | ✅ IMPLEMENTADO |
| ruscadb-static-embeddings | implemented | carga perezosa cacheada + fallback | ✅ IMPLEMENTADO |
| ruscadb-query-cache | implemented | `cached_execute` + invalidación | ✅ IMPLEMENTADO |
| ruscadb-colbert-rerank | implemented | `colbert_rerank.py` + `store.rerank` | ✅ IMPLEMENTADO |
| ruscadb-graph-algorithms | implemented | `graph_algorithms.py` + `store.graph_stats` | ✅ IMPLEMENTADO |
| ruscadb-prepared-statements | implemented | `prepared_statements.py` + `store.prepare` | ✅ IMPLEMENTADO |
| ruscadb-timeseries | implemented | `timeseries_helpers.py` + `store.ts_bucket_sql` | ✅ IMPLEMENTADO |
| ruscadb-rql-advanced | **blocked-upstream** | CTE/UNION/INTERSECT/window → "error de sintaxis" en la DLL actual; requiere feature `sql-std` | 🔴 NO SOPORTADO |
| ruscadb-fts-advanced | implemented | `fts_search_mode` (fuzzy Levenshtein client-side) | ✅ IMPLEMENTADO |
| ruscadb-ivf-pq | **blocked-upstream** | `RabitqQuantizer` existe en Rust pero **no cruza el C-ABI** | 🔴 NO CABLEABLE |
| ruscadb-time-travel | implemented | `execute_at` + `execute_at()`/`Snapshot::at` | ✅ IMPLEMENTADO |
| ruscadb-semantic-cache | implemented (11.53) | `semantic_cache_set/get/delete/entries/purge_expired/metrics` + `SemanticCache` persistente | ✅ IMPLEMENTADO |
| ruscadb-encryption | implemented | `open_encrypted` + `open_encrypted_store` | ✅ IMPLEMENTADO |
| ruscadb-async-io | implemented-parcial (11.53) | `AsyncRuscaDBStore` (thread offload) + `HybridRetriever.aretrieve`; falta actor single-writer | 🟡 PARCIAL |
| ruscadb-mcp-server | **blocked-upstream** | RuscaDB no expone servidor MCP en la DLL (solo 29 símbolos C) | 🔴 NO CABLEABLE |
| ruscadb-mcp-advanced | **blocked-upstream** | depende de `mcp-server` | 🔴 NO CABLEABLE |
| ruscadb-zstd-compression | **blocked-upstream** | feature `compression` no compilada en el DLL actual | 🔴 NO CABLEABLE |
| memory-governance (nuevo, 11.53) | implemented | `_apply_trust_and_recency` + `TRUST_TIER_WEIGHTS` | ✅ IMPLEMENTADO |

## 3. Hallazgos y correcciones (con evidencia)

### H1 (🔴) — Ciclos de import ocultos
- `harness.qa` importaba sus submódulos al final de `__init__` y cada submódulo
  hacía `from harness.qa import QALayer` → ciclo `qa ↔ detector/predictor`.
- **Fix:** tipos extraídos a `harness/qa/types.py`; los 5 submódulos importan de
  ahí; `MCPCommand` se importa de verdad (estaba en `__all__` sin import).
- Evidencia: `check_architecture.py --gate --json` → `"blocking": []`.

### H2 (🔴) — `setattr` de backend en `LanceVectorStore`
- Métodos copiados al objeto, `_db=None` mentido, `delete`/`close`/`full_text_search`
  fuera del contrato.
- **Fix:** `__new__` devuelve el adaptador real; `_LifecycleMixin` (nuevo módulo)
  centraliza `delete`/`delete_collection`/`clear`/`close`; `_delete_lancedb` en
  `backends.py`.
- Evidencia: `test_vector_store_factory.py` (9 passed).

### H3 (🔴) — `_create_store()` roto
- `harness/run_commands/__init__.py:142` importaba `harness.db.vector_store`
  (inexistente) → `RuntimeError` en todo comando que requiriera store.
- **Fix:** usa `get_vector_store()`.

### H4 (🟡) — `SemanticCache` acoplado a internals de LanceDB
- Leía `_lancedb_available`, `_db`, `_mem_collections`; con RuscaDB la ruta
  exacta y el barrido fallaban.
- **Fix:** `_native_lance()`, `_persistent_cache()`, `_uses_lancedb_scores()`;
  hit exacto vía `semantic_cache_get`; borrado vía `semantic_cache_delete`
  (que también purga la fila vectorial); `clear_expired` vía
  `semantic_cache_purge_expired`.
- Evidencia: `test_semantic_cache_persistent.py` (5 passed).

### H5 (🟡) — Recencia y confianza no consumidas en retrieval
- 11.52 etiquetaba `trust_tier` al escribir, pero el retrieval no lo usaba.
- **Fix:** `_apply_trust_and_recency` aplicado a `search`, `full_text_search`,
  `hybrid_search`; cuarentena deny-by-default; `min_trust`;
  `half_life_days` (default documentado 30 d); `_parse_rows` expone
  `created_at`.
- Evidencia: `test_trust_aware_retrieval.py` (14 passed).

### H6 (🟡) — `AsyncRuscaDBStore` sin cablear (0 importers)
- **Fix:** wrapper completo (`search`, `hybrid_search`, `insert`,
  `full_text_search`, `delete`, `execute`, `close`, `async with`,
  `from_path`), exportado en `harness.memory_rag` y usado por
  `HybridRetriever.aretrieve`.
- Evidencia: `test_async_ruscadb.py` (6 passed).

### H7 (🟡) — Gate de arquitectura no aplicado
- **Fix:** `check_architecture.py` con modos `--gate`/`--strict`/`--json`,
  job `architecture` en CI T1 y bloqueo en `.githooks/pre-commit`.
- Evidencia: `OK: 0 violaciones bloqueantes (F1,F2,F4)`; advisory 824
  (deuda legacy de tamaño, declarada).

### H8 (⚪) — `AGENTS.md` / docs desfasados
- Actualizados roadmap, CHANGELOG, MEJORAS y estado de specs a 11.53.

## 3.1 Correcciones de la revisión adversarial (post-commit `ec6f08c7`)

Una revisión independiente del diff detectó 1 BLOCK y 8 WARN; todos corregidos
y cubiertos con tests:

| # | Hallazgo | Fix | Evidencia |
|---|---|---|---|
| B1 | `test_lance_vector_store_init.py` fijaba `VECTOR_BACKEND=lancedb` con `os.environ` a nivel de módulo → contaminaba la suite y rompía los tests de default `ruscadb` | `monkeypatch` en fixture autouse del módulo + fixture de aislamiento en los tests nuevos | `pytest harness/tests -k "default_backend_returns_ruscadb or lance_store_redirects_to_ruscadb"` → 2 passed |
| W1 | Firmas puerto≠adaptador (`query_text` vs `keyword_filter`), invisible para `hasattr` | `LanceVectorStore.hybrid_search` usa `query_text` + alias `keyword_filter`; `search(..., **kwargs)`; F6 compara `inspect.signature` | `check_architecture.py --gate` → F6 OK |
| W2 | `RuscaDBStore.search` ignoraba `filters` (bypass en AgentBus/context_assembler) | `_matches_filters` aplicado en search/FTS/hybrid | `test_search_honors_metadata_filters` |
| W3 | `__new__` degradaba a LanceDB *fail-open* sin `allow_fallback` (DB bloqueada → memoria partida) | distingue librería ausente (degrada) de fallo del motor (fail-fast con WHAT/WHY/WHERE) | `test_ruscadb_failure_without_fallback_fails_fast` / `..._with_fallback_degrades` |
| W4 | `allow_quarantined` no se propagaba en `hybrid_search` | opciones pasadas a `search`/`full_text_search` (RRF resetea score: sin doble ponderación) | `test_hybrid_search_honors_allow_quarantined` |
| W5 | `semantic_cache_clear/delete` devolvían `True` con DELETE fallido | usan `execute()` de bajo nivel y devuelven `False` | `test_semantic_cache_persistent.py` |
| W6 | `semantic_cache_purge_expired` era O(n²) y con cap silencioso de 1000 | un escaneo + borrado por lote (`_semantic_cache_delete_rows`), cap 10000 documentado | tests de caché persistentes |
| W7 | TTL *fail-open* si `cached_at` era ilegible | fail-closed: TTL exigible + fecha ilegible ⇒ expirada | `test_ttl_expiry_returns_none` |
| W8 | F4 ignoraba imports relativos; el CLI pasó a bloquear sin `--gate` | resolución de `level>0` contra el paquete + exclusion del patrón facade; default advise-only restaurado | gate con 0 ciclos reales; `default_exit=0`, `gate_exit=0` |
| N1 | Tests decorativos (asserts no falsables) | asserts concretos (contenido async, valor tras borrar fila exacta, TTL real) | conteos abajo |

> ⚪ Hallazgo extra: al ejecutarse como script, `sys.path[0]` es `scripts/`, por
> lo que F6 podía importar una copia global de `harness`
> (`~/.config/opencode/harness`). El checker ahora fuerza `ROOT` en
> `sys.path` antes de importar.

## 3.2 Cierre de gaps del research (ciclo 11.54)

Se implementaron las capacidades que no dependen de cambios en RuscaDB:

| Gap | Implementación | Test |
|---|---|---|
| Write gate (SSGM) | `RuscaDBStore(memory_guard=...)` + `SWARMIND_MEMORY_GUARD_STRICT=1`; cuarentena o `ValueError` con WHAT/WHY/WHERE | `test_memory_governance.py` (6) |
| Refuerzo por uso | `record_access()` (`last_accessed` + `access_count`); el decaimiento prefiere `last_accessed` | `test_memory_governance.py` |
| Invalidación por versión de caché | `dataset_version` en `_cache_key` + `invalidate_version()` | `test_semantic_cache_version.py` (5) |
| Fail-closed del caché | `SemanticCache(fail_closed=True)` exige `verified=True` (hit exacto y similitud) | `test_semantic_cache_version.py` |
| Actor de escritura único | `WriteActor` (hilo dedicado, cola bounded) + `MemoryBackpressureError`; `write_actor=True` | `test_write_actor.py` (6) |
| Ratchet de deuda | `--ratchet` + `scripts/architecture_baseline.json`; F7 bloquea incrementos | `test_architecture_ratchet.py` (6) |

Con esto, los únicos gaps abiertos son los que exigen cambio upstream
(RaBitQ/IVF-PQ, columnas de gobernanza) o políticas no triviales (evicción por
calor, umbral aprendido, reconciliación programada), documentados en
`docs/research/frontier-2026-10-29.md` §9.1.

## 4. Investigación aplicada

Ver `docs/research/frontier-2026-10-29.md` (6 frentes con fuentes 2023-2026):
OWASP ASI06 / MINJA / SSGM / mnemonic sovereignty, recencia (Park 2023,
MemoryOS 2025), RaBitQ (SIGMOD 2024), caché semántico (vCache ICLR 2026,
MeanCache, GPTCache), single-writer (SQLite WAL, DuckDB), fitness functions
(tach, import-linter, ArchGuard, DORA).

## 5. Verificación ejecutada (evidencia)

| Check | Resultado |
|---|---|
| `ruff check harness scripts` | All checks passed |
| `vulture ... --min-confidence 80` | 0 hallazgos |
| `python scripts/check_architecture.py --gate` | OK (F1/F2/F4/F6) |
| `python scripts/check_architecture.py` (default) | exit 0 (advise-only) |
| `pytest test_vector_store_factory.py` | 11 passed |
| `pytest test_trust_aware_retrieval.py` | 17 passed |
| `pytest test_async_ruscadb.py` | 6 passed |
| `pytest test_semantic_cache_persistent.py` | 6 passed |
| Lote memoria (11 archivos) | 239 passed, 17 skipped |
| Lote retrieval/compactación (6 archivos) | 74 passed |
| Lote buses/run_commands (5 archivos) | 163 passed |
| Lote gates tras review (6 archivos) | 130 passed |
| `pytest --collect-only -q` | 7236 tests |

## 6. Pendientes (siguiente ciclo)

1. **Actor de escritura único** con cola bounded y backpressure tipado
   (`asyncio.Queue` + worker dedicado) — P1.
2. **Ratchet de deuda F3/F5**: congelar los 824 hallazgos y bloquear solo
   incrementos (patrón `tach unchecked`).
3. **`last_accessed` + refuerzo por uso** en recencia (MemoryBank/MemoryOS).
4. **Invalidación por `dataset_version`** y umbral fail-closed en caché.
5. **Re-exponer RaBitQ/MCP/zstd**: requiere cambios en RuscaDB (FFI), fuera del
   alcance de SWARMIND; specs marcados `blocked-upstream`.
