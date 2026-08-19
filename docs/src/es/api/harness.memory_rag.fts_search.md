<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.fts_search`

FTS Search â€” Full-text search sobre memoria (inspirado en FTS5 de Hermes Agent).

## `FTSSearch`

Full-text search sobre documentos indexados.

### `index(doc\_id: str, content: str, metadata: dict[str, Any] \| None = None, domain: str = 'general') -> bool`

Indexa un documento para busqueda full-text.

### `index\_batch(documents: list[tuple[str, str, dict[str, Any] \| None, str]]) -> int`

Indexa multiples documentos en batch.

### `search(query: str, top\_k: int = 10, domain\_filter: str \| None = None) -> list[dict[str, Any]]`

Busca documentos por contenido full-text.

### `delete(doc\_id: str) -> bool`

Delete a document from the index.

### `clear() -> None`

Clear all indexed documents.

### `get\_stats() -> dict[str, Any]`

Get search index statistics.

### `close() -> None`

Close the database connection.
