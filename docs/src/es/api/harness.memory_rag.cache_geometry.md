<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.cache_geometry`

CacheGeometry — Cache Geometry Discipline (ADR-0034).

## `CacheGeometry`

Reordenador y medidor de geometría de cache.

### `classify(text: str) -> str`

Clasifica un bloque como "static" o "dynamic".

### `reorder(blocks: list[str]) -> list[str]`

Reordena bloques: estáticos primero, dinámicos después.

### `static\_prefix(blocks: list[str]) -> list[str]`

Retorna solo los bloques estáticos (el prefijo cacheable).

### `static\_prefix\_hash(blocks: list[str]) -> str`

Hash SHA-256 del prefijo estático concatenado.

### `report(requests: list[dict]) -> dict`

Reporte de geometría sobre una serie de requests.
