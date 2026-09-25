<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.embedding_service`

embedding\_service.py â€” Servicio de embeddings con batching inteligente.

## `BatchedEmbeddingService`

Servicio de embeddings con batching temporal.

### `embed(text: str) -> np.ndarray`

Embed un texto (async con batching).

### `embed\_sync(text: str) -> np.ndarray`

Embed un texto en modo sync (sin batching).

### `embed\_batch\_sync(texts: list[str]) -> np.ndarray`

Embed una lista de textos en batch (modo sync).

### `get\_stats() -> dict[str, Any]`

Return service statistics.
