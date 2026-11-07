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
| Búsqueda binaria (`search_binary`) | sí | **solo tests** | Exponer en `!db health` (stats); falta elegirla por presupuesto |
| Blobs (`put/get/attach/gc`) | sí | **solo tests** | `!db gc`; falta ingesta multimodal que los use |
| Backup / integridad / LSN | sí | **sin superficie CLI** | `!db backup`, `!db health`, `!db stats` |
| Cache de consultas | sí | interno, sin métricas visibles | `!db health`/`!db stats` |
| `explain`, time-travel, cifrado | sí | **sin uso** | Roadmap (requiere decisión de UX) |
| FTS avanzado (`fts_search_mode`) | sí | **sin uso** | Roadmap (exponer `--mode`) |
| ColBERT rerank (`rerank`) | sí | **sin uso** | Roadmap (coste/beneficio) |
| Async store | sí | **solo tests** | Roadmap (I/O concurrente real) |
| Prepared nativo / KNN USING / 3VL / RCOL1 | upstream | **DLL 2026-10-29 no exporta** | `!db capabilities` lo reporta; rebuild pendiente |
| MCP server de RuscaDB | upstream | **sin uso** | Roadmap (puente MCP) |

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
  `!db stats` (store real), `!db backup <ruta>`, `!db gc`, `!db reconcile`.
- `harness/run.py`: usa la factory (`_create_store`) en daemon, `!db` y modo
  tarea; ya no fuerza LanceDB.
- `ruscadb.py`: `_CAPABILITY_NAMES` incluye `prepare`/`execute_prepared`/
  `search_quantized`/`search_filtered` para reportar la DLL real.
- `harness/tests/test_ruscadb_utilization.py` (9) + ajustes de tests de `run`.

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

1. **Rebuild DLL** (`cargo build -p ruscadb-ffi`) y cablear prepared nativo +
   `KNN USING FILTERED/EXACT` con contrato en `test_ruscadb_store.py`.
2. **Búsqueda binaria adaptativa**: elegir `search_binary` cuando el presupuesto
   de memoria/tiempo lo justifique; medir recall@k vs `search`.
3. **Blobs multimodales**: usar `attach_blob` en ingesta de PDF/imágenes y
   `gc_blobs` periódico.
4. **`!db explain <sql>`** y `!db time-travel <tx>` (APIs ya listas).
5. **MCP**: registrar `ruscadb mcp` como plugin MCP para que los agentes usen
   SQL/FTS/grafo directamente.
6. **Async**: usar `AsyncRuscaDBStore` en ingestas largas (no bloquea el loop).
