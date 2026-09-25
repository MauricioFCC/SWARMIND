<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.hermes_bridge`

Hermes Bridge â€” puente de integraciÃ³n con shared\_memory.

## `HermesBridge`

Puente de integraciÃ³n con shared\_memory.

### `sync\_to\_hermes(records: list[dict]) -> int`

Sincroniza registros desde Swarmind hacia Hermes.

### `sync\_from\_hermes(pattern: str = '\*.json') -> list[dict]`

Sincroniza registros desde Hermes hacia Swarmind.

### `sync\_skills\_to\_hermes(skills\_dir: str) -> int`

Sincroniza skills de Swarmind hacia Hermes.

### `get\_memory\_service()`

Obtiene una instancia de MemoryService de Hermes.

### `get\_quality\_service()`

Obtiene una instancia de QualityService de Hermes.

### `get\_status() -> dict`

Obtiene estado del bridge.
