<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.reversible_compaction`

CCR reversible — Compress-Cache-Retrieve (Headroom, ADR-0033).

### `bm25\_like\_search(original: str, query: str, top\_k: int = 5) -> list[str]`

Busqueda BM25-like simple: puntua lineas por tokens de query presentes.

## `ReversibleCompactor`

CCR reversible: compacta, cachea el original y permite recuperarlo.

### `compact(text: str, budget\_ratio: float = 0.6, min\_chars: int = 50) -> tuple[str, str, str]`

Compacta el texto, cachea el original y retorna (compacto, hash, original).

### `retrieve(hash\_id: str, query: str = '') -> str \| None`

Recupera el original por hash, con busqueda BM25-like opcional.

### `retrieve\_full(hash\_id: str) -> str \| None`

Recupera el original completo por hash.

### `stats() -> dict`

Resume las metricas del compactor.
