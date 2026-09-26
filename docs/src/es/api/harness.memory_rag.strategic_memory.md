<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.strategic_memory`

StrategicMemory — Memoria con forget estrategico (SF-AMS).

## `MemoryItem`

Item individual de memoria strategic.

## `StrategicMemory`

Memoria compartida con olvido estrategico basado en utilidad.

### `store(key: str, value: Any, tags: list[str] \| None = None, entities: list[str] \| None = None) -> None`

Almacena un valor en memoria asociado a una clave.

### `recall(key: str) -> Any \| None`

Recupera un valor por su clave.

### `search\_by\_tags(tags: list[str]) -> list[MemoryItem]`

Busca items que contengan al menos una de las etiquetas.

### `search\_by\_entities(entities: list[str]) -> list[MemoryItem]`

Busca items que contengan al menos una de las entidades.

### `get\_stats() -> dict[str, Any]`

Retorna estadisticas actuales de la memoria.

### `clear() -> None`

Elimina todos los items de la memoria y persiste el estado vacio.

### `contains(key: str) -> bool`

Verifica si una clave existe en memoria.
