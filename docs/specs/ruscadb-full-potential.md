# Spec — Potencial completo de RuscaDB en SWARMIND (ciclo 11.45)

> Estado: implemented (ciclo 11.45) — Dueño: harness/memory_rag — Frontera: 2026-10.

## 1. Objetivo

Que SWARMIND aproveche en totalidad las capacidades del motor RuscaDB (multi-modelo
+ vectorial + FTS + grafo + blob + MVCC + operacional), no solo el subconjunto
vectorial inicial, y que la integracion sea segura, portable y degradante.

## 2. Capacidades integradas

| Capacidad RuscaDB | Integracion SWARMIND | Modulo |
|---|---|---|
| Relacional + indices secundarios | `create_collection` crea indices sobre `id` y `created_at`; `create_index` publico. | `ruscadb_store.py` |
| Documental (metadata JSON) | Metadata persistida como `metadata` Text + derivacion `text` para FTS. | `ruscadb_store.py` |
| Vectorial HNSW + KNN | `search` usa `KNN embedding <|k|> [...]`. | `ruscadb_store.py` |
| FTS BM25 | `full_text_search` usa `MATCH(text, ...)` (fallback `metadata`). | `ruscadb_store.py` |
| Grafo CSR | `graph_traverse` nativo + BFS por RecordId; edges en insert. | `ruscadb_store.py` |
| Multimodal (blob CAS) | `put_blob`/`get_blob`/`gc_blobs`/`attach_blob`. | `ruscadb.py`, `ruscadb_store.py` |
| MVCC update/delete por RecordId | `update_record`/`delete_record`/`get_record` via ULID; `_rid_map`. | `ruscadb.py`, `ruscadb_store.py` |
| Operacional | `integrity`, `backup`, `current_lsn`, `explain`. | `ruscadb_store.py` |
| Solo lectura | `open_with_options(..., readonly=True)`. | `ruscadb.py` |
| Blob store opcional | `open_with_options(..., blob_path=...)`. | `ruscadb.py` |

## 3. Extension del C-ABI

Se extendio `RuscaDB/crates/ruscadb-ffi/src/lib.rs` con:

`ruscadb_open_opts`, `ruscadb_create_index`, `ruscadb_update_record`,
`ruscadb_delete_record`, `ruscadb_last_affected`, `ruscadb_get_record`,
`ruscadb_put_blob`, `ruscadb_blob_len`, `ruscadb_get_blob`, `ruscadb_gc_blobs`,
`ruscadb_last_lsn`, `ruscadb_integrity_check`, `ruscadb_backup`,
`ruscadb_explain`.

El binding Python en `harness/memory_rag/ruscadb.py` enlaza estas funciones de
forma **opcional** (`_bind_optional`), de modo que una DLL antigua sigue
funcionando en el subconjunto basico.

## 4. Seguridad

- `_safe_ident` valida nombres de tabla/columna con `^[A-Za-z_][A-Za-z0-9_]*$`.
- `_escape_literal` duplica comillas simples en literales RQL.
- `delete`/`update` usan RecordId (ULID) cuando esta disponible, evitando
  interpolacion de id logico.

## 5. Frontier (RAG)

- `AdaptiveRetriever` (arXiv:2403.14403): seleccion de estrategia por complejidad.
- `GraphRAGRetriever` (arXiv:2410.05779 / arXiv:2404.16130): recuperacion
  dual-level BM25 + grafo con RRF.
- `SummaryCommunication` (arXiv:2607.27942): contexto compacto basado en resumenes.

## 6. Comandos

- `!rag search <consulta>` — recuperacion dual-level (GraphRAG).

## 7. Outcome medible

- `pytest harness/tests/test_ruscadb_store.py -q` — 11 passed.
- `pytest harness/tests/test_graph_rag_retriever.py -q` — 7 passed.
- `pytest harness/tests/test_adaptive_retriever.py -q` — 4 passed.
- `ruff check harness/ scripts/` — 0 errores.
- `vulture ...` — 0 dead code.
