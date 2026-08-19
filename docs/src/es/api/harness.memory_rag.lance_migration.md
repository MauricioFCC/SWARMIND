<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.lance_migration`

LanceDB Migration — Lógica de migración de colecciones LanceDB.

### `generate\_sample\_row(collection\_name: str) -> dict[str, Any]`

Genera una fila sample con todas las columnas que una colección puede necesitar.

### `diff\_schemas(old\_schema: dict[str, str], new\_schema: dict[str, str]) -> dict[str, list[str]]`

Compara dos schemas y retorna diferencias.

### `serialize\_for\_schema(value: Any) -> Any`

Convierte valores no-primitivos a strings JSON para compatibilidad con schema LanceDB.

### `adapt\_vector(vec: Any, target\_dim: int) -> Any`

Trunca o paddea un vector a una dimensión objetivo.
