<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.memory_config`

Memory Configuration — configuración modular del sistema de memoria.

## `MemoryBackend(str, Enum)`

_Sin docstring._

## `TelemetryLevel(str, Enum)`

_Sin docstring._

## `MemoryConfig`

Configuración completa del sistema de memoria.

### `to\_dict() -> dict`

_Sin docstring._

### `from\_dict(d: dict) -> MemoryConfig`

_Sin docstring._

### `from\_env() -> MemoryConfig`

Carga configuración desde variables de entorno.

### `get\_memory\_config() -> MemoryConfig`

Obtiene la configuración global de memoria.

### `set\_memory\_config(config: MemoryConfig) -> None`

Establece la configuración global de memoria.

### `reset\_memory\_config() -> None`

Resetea la configuración global a valores de entorno.
