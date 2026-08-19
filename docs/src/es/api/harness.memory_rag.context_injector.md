<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.context_injector`

context\_injector.py — Inyeccion automatica de contexto en subtareas.

## `ContextInjector`

Inyecta recordatorio de estandares en descripciones de subtareas.

### `inject(description: str, agent\_role: str = 'builder') -> str`

Inyecta estandares en una descripcion de subtarea.

### `get\_reminder(agent\_role: str = 'builder') -> str`

Obtiene recordatorio de estandares para un rol.

### `estimate\_tokens(agent\_role: str = 'builder') -> int`

Estima tokens adicionales por inyeccion.

### `batch\_inject(descriptions: list[str], agent\_role: str = 'builder') -> list[str]`

Inyecta estandares en multiples descripciones.

### `validate\_docstrings(code: str, file\_path: str = '<string>') -> list[str]`

Valida que todo codigo tenga docstring ES-UTF8 completo.
