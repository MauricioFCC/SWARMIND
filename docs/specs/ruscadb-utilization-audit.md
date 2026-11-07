# Auditoría — aprovechamiento de RuscaDB por Swarmind (2026-11-06)

> Estado: **auditoría aplicada** (v1.0.0). Alcance: capa Python
> (`harness/memory_rag`) y su uso real por CLI/runtime; no modifica el motor
> Rust de RuscaDB.

## 1. Qué existe (implementación)

`harness/memory_rag/ruscadb.py` (C-ABI) expone 44 funciones; `ruscadb_store.py`
(2.3k líneas) implementa SQL, CRUD, búsqueda vectorial, binaria/cuantizada, FTS,
híbrida, grafo, blobs, cache de consultas, cache semántico, time-travel,
backup, integridad, LSN, `explain`, cifrado, gobernanza y reconciliación.
`vector_store_factory` declara **RuscaDB como backend por defecto**.

## 2. Hallazgos de aprovechamiento

| Capacidad | Implementada | Uso real antes | Acción |
|---|---|---|---|
| SQL/vector/CRUD | sí | sí (factory, RAG, memoria) | — |
| FTS (`full_text_search`) | sí | sí (GraphRAG/hybrid) | — |
| Grafo (`graph_traverse`) | sí | sí (`GraphRAGRetriever`) | — |
| Cache semántico | sí | sí (`semantic_cache/ops.py`) | — |
| Búsqueda binaria (`search_binary`) | sí | solo tests | `search_adaptive` + `!db health` (stats) + benchmark |
| KNN cuantizado (`search_quantized`) | sí (DLL 2026-11-06) | no existía | `search_quantized` con fallback binario |
| KNN filtrado ACORN (`search_filtered`) | sí (DLL 2026-11-06) | no existía | `search_filtered` con resolución `logical_id→RecordId` |
| Blobs (`put/get/attach/gc`) | sí | solo tests | ingesta adjunta el original (≤8 MiB) + `!db gc` |
| Backup / integridad / LSN | sí | sin superficie CLI | `!db backup`, `!db health`, `!db stats` |
| Cache de consultas | sí | interno, sin métricas visibles | `!db health`/`!db stats` |
| `explain`, time-travel | sí | sin uso | `!db explain <sql>` y `!db time-travel <tx> <sql>` |
| FTS avanzado + rerank | sí | sin uso | `!rag search --mode exact\|fuzzy --rerank` |
| Async store | sí | solo tests | métodos async para quantized/filtered/adaptive |
| Prepared nativo | crate sí / FFI no | — | `!db capabilities` lo reporta; recomendación upstream R1 |
| 3VL / RCOL1 / cifrado | sí | sin uso | evaluar tras estabilizar el ABI |
| MCP server de RuscaDB | upstream | sin uso | entrada MCP `ruscadb` (disabled) documentada |

### Bug de utilización encontrado

`harness/run.py` instanciaba **`LanceVectorStore()`** en el modo tarea, daemon y
`!db`, ignorando que la factory ya declara RuscaDB por defecto. Es decir, el CLI
interactivo no aprovechaba RuscaDB aunque estuviera instalado. **Corregido**:
ahora usa `_create_store()` (factory, RuscaDB por defecto, Lance como fallback).

Además `!db stats` usaba `DBMigrator` (LanceDB) en vez del store activo.

## 3. Cambios aplicados

- `harness/memory_rag/ruscadb_capabilities.py`: `probe()` con 22 features y sus
  símbolos del C-ABI, faltantes y recomendación de rebuild; `!db capabilities`.
- `harness/run_commands/handlers_ruscadb.py`: `!db capabilities`, `!db health`,
  `!db stats` (store real), `!db backup <ruta>`, `!db gc`, `!db reconcile`,
  `!db explain <sql>` y `!db time-travel <tx> <sql>`.
- `harness/run.py`: usa la factory (`_create_store`) en daemon, `!db` y modo
  tarea; ya no fuerza LanceDB.
- `ruscadb.py`: bindings de `search_quantized`/`search_filtered` con reintento
  de buffer; `_CAPABILITY_NAMES` incluye `prepare`/`execute_prepared`.
- `ruscadb_store.py`: `search_quantized`, `search_filtered` (ACORN, resolviendo
  `logical_id → RecordId`) y `search_adaptive` con degradación explícita.
- `doc_ingester.py`: `attach_source_blob` adjunta el PDF/imagen original al
  primer chunk (≤8 MiB) para que `get_blob`/`gc_blobs` tengan uso real.
- `async_ruscadb.py`: API async para quantized/filtered/adaptive.
- UX: `!rag search --mode exact|fuzzy --rerank`; entrada MCP `ruscadb`.
- `scripts/bench_ruscadb_search.py`: recall@k y latencia por estrategia.
- Tests: `test_binary_search` (15), `test_async_ruscadb` (7),
  `test_ruscadb_utilization` (13).

## 4. ACs verificables

| AC | Criterio | Test |
|---|---|---|
| RU-1 | `probe` distingue DLL completa/antigua y recomienda rebuild | `TestCapabilities` |
| RU-2 | `!db capabilities` lista features y faltantes | `test_capabilities` |
| RU-3 | `!db health` usa integrity/LSN/cache/binario/grafo | `test_health` |
| RU-4 | `!db stats` cuenta colecciones del store, no del migrador | `test_stats_usa_store` |
| RU-5 | `!db backup/gc/reconcile` llaman al store | `test_backup_y_gc`, `test_reconcile` |
| RU-6 | los comandos están en la tabla canónica | `test_comandos_en_la_tabla` |
| RU-7 | el CLI usa la factory (RuscaDB por defecto) | `test_run.py` (patch `_create_store`) |

## 5. Siguientes pasos priorizados

1. **Prepared nativo**: `ruscadb-ffi` aún no exporta `prepare`/`execute_prepared`;
   propuesta y contrato en `RuscaDB/docs/RECOMENDACIONES-SWARMIND.md` (R1).
   Cablearlo cuando el ABI los publique.
2. **Búsqueda adaptativa con datos**: `scripts/bench_ruscadb_search.py` mide
   recall@k y p50/p95 por estrategia; falta usar el presupuesto real del host
   para elegir `exact|binary|quantized|filtered` automáticamente.
3. **Blobs multimodales**: la ingesta adjunta el original (≤8 MiB) y hay
   `gc_blobs`; falta extracción/OCR para indexar el contenido del PDF/imagen.
4. **Async en runtime**: los métodos async existen; falta un caller de
   producción (ingesta larga o daemon) que los use.
5. **MCP**: entrada `ruscadb` registrada pero deshabilitada; requiere `--db`,
   contrato de escritura y autorización.
6. **3VL / RCOL1 / cifrado**: evaluar tras cerrar el ABI y documentar símbolos
   por versión (R7).
