<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.memory_guard`

Memoria compartida gobernada (PatchBoard/MemClaw/MAPLE-Guard, ADR-0039 #7).

## `MemoryGuard`

Guarda de escritura/lectura sobre memoria compartida por agentes.

### `register\_schema(collection: str, schema: dict[str, type]) -> None`

Registra (o reemplaza) el schema de gobierno para una coleccion.

### `get\_schema(collection: str) -> dict[str, type]`

Schema efectivo de una coleccion: registrado o default minimal.

### `guard\_write(collection: str, record: dict, schema: dict[str, type] \| None = None) -> dict`

Valida y limpia un record antes de escribirlo en memoria compartida.

### `guard\_retrieval(collection: str, query: str) -> bool`

Decide si un retrieval sobre la coleccion esta permitido.

### `validate(collection: str, record: dict, schema: dict[str, type] \| None = None) -> list[str]`

Diagnostico estricto: lista todos los errores del record vs schema.
