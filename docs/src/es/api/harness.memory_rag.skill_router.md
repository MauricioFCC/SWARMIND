<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.skill_router`

skill\_router.py — Router semantico de skills via LanceDB.

## `SkillRouter`

Router semantico de skills.

### `route(message: str, max\_skills: int = MAX\_SKILLS\_PER\_TASK) -> list[str]`

Encuentra los skills mas relevantes para un mensaje.

### `build\_context(skill\_names: list[str]) -> str`

Construye contexto SOLO para los skills seleccionados.

### `estimate\_tokens(skill\_names: list[str]) -> int`

Estima tokens que consumiran los skills seleccionados.

### `get\_available\_skills() -> list[str]`

Retorna lista de todos los skills disponibles.
