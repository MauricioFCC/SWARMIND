# Spec — Optimizacion frontier de SWARMIND via capacidades RuscaDB no integradas

> Estado: proposed — Dueño: harness/memory_rag — Frontera: 2026-10.
> Fuente: repositorio RuscaDB (specs/ + docs/), HEAD 4b299cc (Ola 10 Frontier II).
> Alcance: mapear las capacidades de RuscaDB que SWARMIND aun no aprovecha y
> definir el plan de integracion. NO implementa; solo especifica.
>
> **Estado 2026-10-29 (ciclo 11.53)**: fases A y B cerradas salvo lo que el
> C-ABI no expone. Implementado: FTS avanzado, ColBERT rerank, graph algorithms,
> query cache, static embeddings, time travel, prepared statements, cache
> semantico persistente, async I/O (thread offload). **Bloqueado upstream (sin
> simbolo en la DLL, 29 funciones): IVF-PQ/RaBitQ, MCP server, zstd/WAL
> compression, RQL avanzado (feature `sql-std`).** Ver
> `docs/specs/audit-implementacion-2026-10-29.md`.


## 1. Inventario de capacidades RuscaDB no integradas en SWARMIND

### 1.1 Retrieval avanzado
| Capacidad RuscaDB | Spec RuscaDB | Estado SWARMIND | Oportunidad |
|---|---|---|---|
| ColBERT reranking (late interaction) | `colbert_rerank.md` | No integrado | Reranking de resultados KNN/FTS con cross-encoder ligero (MaxSim). |
| IFVS (pre/in/post filtering por selectividad) | `ifvs_executor.md`, `ifvs_hnsw.md` | No expuesto | Filtros `WHERE` sobre KNN ya delegados al motor; verificar selectividad. |
| IVF-PQ (cuantizacion de vectores) | `ivf_pq.md`, `ivf_clustering.md` | No integrado | Reducir memoria de embeddings en 4-8x. |
| RaBitQ quantization | `rabitq_quantization.md` | No integrado | Cuantizacion 1-bit para busqueda rapida. |
| HNSW budget/PQ | `hnsw_budget_pq.md` | No integrado | Control de memoria del indice HNSW. |
| FTS avanzado (fuzzy, phrase, stemming) | `fts_advanced.md`, `fts_fuzzy_scoring.md`, `fts_proximity.md`, `fts_prefix.md` | Parcial (MATCH basico) | Fuzzy matching Levenshtein + phrase + stemming Snowball. |
| BlockMax WAND | `blockmax_wand.md` | No integrado | Aceleracion de BM25 top-k. |
| Hybrid retrieval (multi-stage) | `hybrid_retrieval.md` | Parcial (RRF) | Pipeline de stages con pesos aprendidos. |

### 1.2 RQL avanzado
| Capacidad | Spec | Estado | Oportunidad |
|---|---|---|---|
| Subqueries | `rql_subqueries.md` | No usado | Consultas anidadas para agregaciones complejas. |
| CTE (WITH) | `rql_cte.md` | No usado | Consultas recursivas para grafos. |
| Window functions | `rql_window_functions.md` | No usado | Ranking, moving avg sobre resultados. |
| Set operations (UNION/INTERSECT/EXCEPT) | `rql_set_operations.md` | No usado | Combinar resultados de multiples colecciones. |
| Expression language | `rql_expression_language.md` | No usado | Calculos en SELECT. |
| Prepared statements | `prepared_statements.md`, `prepared_statements_real.md` | No usado | Evitar re-parseo en queries repetidas. |

### 1.3 Time travel / MVCC
| Capacidad | Spec | Estado | Oportunidad |
|---|---|---|---|
| execute_at (snapshot por LSN) | `time_travel.md`, `time_travel_real.md` | No integrado | Reproducibilidad de retrieval en un punto del tiempo. |
| Serialisable snapshot isolation | `serializable_snapshot_isolation.md` | No integrado | Consistencia fuerte para multi-agente. |
| MVCC soft delete + GC | `mvcc_soft_delete.md`, `mvcc_gc_real.md`, `mvcc_reaper.md` | Parcial (delete logico) | Purga fisica de versiones muertas. |
| Epoch-based reclamation | `epoch_based_reclamation.md` | No integrado | Reclamacion de memoria de versiones antiguas. |

### 1.4 Caching
| Capacidad | Spec | Estado | Oportunidad |
|---|---|---|---|
| Semantic cache persistente | `semantic_cache.md`, `semantic_cache_persistence.md` | Parcial (SWARMIND tiene el suyo) | Delegar al cache persistente de RuscaDB. |
| Query result cache | `query_result_cache.md` | No integrado | Cachear resultados de RQL frecuentes. |

### 1.5 Multimodal / Blobs
| Capacidad | Spec | Estado | Oportunidad |
|---|---|---|---|
| Blob pipeline (async) | `blob_pipeline.md` | No integrado | Ingesta asincrona de blobs. |
| Blob GC | `blob_gc.md` | Integrado (gc_blobs) | OK. |

### 1.6 Grafos
| Capacidad | Spec | Estado | Oportunidad |
|---|---|---|---|
| Graph algorithms (PageRank, centrality, shortest path) | `graph_algorithms.md` | No integrado | Ranking de nodos por importancia. |
| Graph store (CSR) | `graph_store.md` | Integrado (TRAVERSE) | OK. |

### 1.7 Time series
| Capacidad | Spec | Estado | Oportunidad |
|---|---|---|---|
| Time series (bucketing, ventanas, resampling) | `time_series.md`, `ts_advanced.md`, `ts_continuous_aggregates.md`, `ts_retention.md`, `ts_facade.md` | No integrado | Analitica temporal de metricas de agentes. |
| Downsampling | `ts_advanced.md` | No integrado | Reducir volumen de series temporales. |

### 1.8 Observabilidad / Operacional
| Capacidad | Spec | Estado | Oportunidad |
|---|---|---|---|
| OTEL exporter | `otel_exporter.md`, `otel_real.md` | No integrado | Trazas distribuidas. |
| Observability registry (Prometheus) | `observability.md` | No integrado | Metricas de latencia/throughput. |
| Audit persistence + RBAC | `audit_persistence.md`, `audit_rbac.md` | No integrado | Auditoria de operaciones de memoria. |
| Online/incremental/S3 backup | `online_backup.md`, `incremental_backup.md`, `s3_backup.md`, `backup_verification.md` | Parcial (backup local) | Backup remoto e incremental. |

### 1.9 Async I/O
| Capacidad | Spec | Estado | Oportunidad |
|---|---|---|---|
| Async I/O | `async_io.md` | No integrado | Operaciones de memoria no bloqueantes. |

### 1.10 Compresion
| Capacidad | Spec | Estado | Oportunidad |
|---|---|---|---|
| Zstd compression (WAL) | `zstd_compression.md`, `zstd_real.md`, `wal_compression.md` | No integrado (feature off) | Reducir tamano del WAL. |
| Alp compression | `alp_compression.md` | No integrado | Compresion de series temporales. |

### 1.11 Seguridad
| Capacidad | Spec | Estado | Oportunidad |
|---|---|---|---|
| Cifrado en reposo (XChaCha20 + Argon2id) | `crypto.md`, `encrypted_at_rest.md` | No integrado | Proteccion de la memoria central. |
| KMS/HSM externo | `kms_hsm_external.md` | No integrado | Gestion de claves en produccion. |
| Post-quantum crypto | `post_quantum_crypto.md` | No integrado | Futuro. |

### 1.12 MCP
| Capacidad | Spec | Estado | Oportunidad |
|---|---|---|---|
| MCP server (tools + resources) | `mcp_server.md`, `mcp_advanced_write.md`, `mcp_write_tools.md` | No integrado | Exponer RuscaDB como MCP server a agentes. |

### 1.13 Embeddings
| Capacidad | Spec | Estado | Oportunidad |
|---|---|---|---|
| Static embeddings (model2vec) | `static_embeddings.md`, `ai_embed.md`, `ai_embedder.md` | No integrado | Embeddings locales sin red. |
| Embedding registry | `embedding_registry.md` | No integrado | Registro de modelos de embedding. |
| ONNX inference | `onnx_inference.md` | No integrado | Inferencia local de cross-encoder. |

## 2. Plan de integracion priorizado (por impacto)

### Fase A — Alto impacto, bajo esfuerzo (1-2 semanas)
1. **FTS avanzado**: activar feature `fts-advanced` y usar fuzzy/phrase/stemming en `full_text_search`.
2. **ColBERT reranking**: rerank top-k de hybrid_search con MaxSim.
3. **Graph algorithms**: PageRank/centrality para ranking de nodos en GraphRAG.
4. **Query result cache**: cachear resultados de RQL frecuentes.
5. **Static embeddings**: embeddings locales via model2vec (sin red).

### Fase B — Medio impacto (2-4 semanas)
6. **IVF-PQ / RaBitQ**: cuantizacion de vectores para reducir memoria.
7. **Time travel (execute_at)**: reproducibilidad de retrieval.
8. **Semantic cache persistente**: delegar al cache de RuscaDB.
9. **Prepared statements**: evitar re-parseo.
10. **MCP server**: exponer RuscaDB como MCP.

### Fase C — Largo plazo (1-2 meses)
11. **Time series**: analitica temporal de metricas.
12. **Cifrado en reposo**: proteccion de memoria central.
13. **Async I/O**: operaciones no bloqueantes.
14. **Zstd compression**: reducir WAL.
15. **RQL avanzado**: CTE, subqueries, window functions.

## 3. Specs a crear en SWARMIND (uno por capacidad priorizada)

Cada spec debe seguir el formato SDD (objetivo, outcome medible, exit criteria,
owner, frontera). Se crearan en `docs/specs/` con prefijo `ruscadb-`.

Lista de specs a generar:
- `ruscadb-fts-advanced.md`
- `ruscadb-colbert-rerank.md`
- `ruscadb-graph-algorithms.md`
- `ruscadb-query-cache.md`
- `ruscadb-static-embeddings.md`
- `ruscadb-ivf-pq.md`
- `ruscadb-time-travel.md`
- `ruscadb-semantic-cache.md`
- `ruscadb-prepared-statements.md`
- `ruscadb-mcp-server.md`
- `ruscadb-timeseries.md`
- `ruscadb-encryption.md`
- `ruscadb-async-io.md`
- `ruscadb-zstd-compression.md`
- `ruscadb-rql-advanced.md`

## 4. Notas de compatibilidad

- Las features opcionales de RuscaDB (fts-advanced, compression, onnx, etc.)
  requieren compilar la DLL con los feature flags correspondientes.
  `setup_swarmind.py` debe soportar `--features` para pasarlos a cargo.
- El C-ABI actual (13 funciones + 12 extendidas) no expone todas las
  capacidades (ej. time travel, prepared statements, async). Requieren
  extension del FFI (como se hizo en ciclo 11.45).

## 5. Outcome medible (global)

- Cobertura de capacidades RuscaDB en SWARMIND: de ~30% actual a >= 80%.
- Latencia de retrieval p95 < 30ms (con ColBERT + IFVS).
- Memoria de embeddings reducida en >= 4x (IVF-PQ).
- Cache hit rate >= 70%.

## 6. Esfuerzo estimado

- Fase A: 2 semanas.
- Fase B: 4 semanas.
- Fase C: 2 meses.
