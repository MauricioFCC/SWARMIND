<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.kv_cache_sharing`

KVCacheSharing — Comparticion de KV Cache entre agentes secuenciales.

## `KVCacheEntry`

Entrada de KV cache compartido.

## `KVCacheStats`

Estadisticas del KV cache compartido.

## `KVCacheSharing`

Cache compartido de KV entre agentes, thread-safe.

### `store(prompt: str, model: str, agent\_id: str, token\_count: int = 1024) -> str`

Almacena un KV cache.

### `get(prompt: str, min\_prefix: int = 10) -> KVCacheEntry \| None`

Recupera un KV cache por prompt exacto o prefijo.

### `get\_stats() -> KVCacheStats`

Retorna estadisticas del cache.

### `clear() -> int`

Limpia todo el cache.
