<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.persistent_memory`

PersistentMemory - Memoria cross-session tipo Engram para Swarmind.

## `MemoryEntry`

Entrada de memoria persistente.

## `PersistentMemory`

Memoria persistente cross-session.

### `store(key: str, value: Any, agent: str = 'system', session\_id: str = 'default', ttl: int = 0) -> None`

Almacenar un valor en memoria persistente.

### `recall(key: str) -> Any \| None`

Recuperar un valor por clave.

### `get\_session(session\_id: str) -> dict[str, Any]`

Recuperar todo el contexto de una sesion.

### `get\_agent\_memory(agent: str) -> dict[str, Any]`

Recuperar toda la memoria de un agente.

### `get\_all\_entries() -> dict[str, MemoryEntry]`

Obtener todas las entradas (para inspeccion).

### `get\_stats() -> dict[str, Any]`

Estadisticas de memoria.

### `clear() -> None`

Limpiar toda la memoria.
