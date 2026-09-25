<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.shaped_cache`

shaped\_cache — Cache con forma activa: LRU + TTL + relevancia.

## `ShapedCache`

Cache con forma activa: LRU + TTL + relevancia.

### `get\_shaped(prompt: str, threshold: float = DEFAULT\_SIMILARITY\_THRESHOLD, context\_window: int \| None = None) -> dict[str, Any] \| None`

Obtener respuesta del cache con forma activa.

### `set\_shaped(prompt: str, response: str, metadata: dict[str, Any] \| None = None, token\_cost: int = 0) -> str`

Almacenar respuesta en cache con forma activa.

### `clear\_expired() -> int`

Limpiar entradas expiradas por TTL.

### `get\_stats() -> dict[str, Any]`

Metricas de uso del cache con forma.
