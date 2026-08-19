<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.shared_cache`

SharedSemanticCache — Cache semantico compartido entre agentes.

## `CacheEntry`

Entrada individual en el cache compartido.

## `CacheStats`

Estadisticas del cache compartido.

## `SharedSemanticCache`

Cache semantico compartido entre agentes con thread-safety.

### `get(text: str, agent\_id: str = '') -> str \| None`

Busca un resultado en cache por similitud semantica.

### `set(text: str, result: str, model: str, agent\_id: str = '') -> str`

Almacena un resultado en cache.

### `get\_stats() -> CacheStats`

Retorna estadisticas del cache.

### `clear() -> int`

Limpia todo el cache.
