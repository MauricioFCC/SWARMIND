<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.skill_minifier`

Skill Minifier — Optimiza skills para eficiencia de tokens.

## `SkillMinifier`

Comprime SKILL.md files para reducir tokens.

### `minify(content: str) -> str`

Comprime un SKILL.md completo.

### `minify\_file(src\_path: str, dst\_path: str \| None = None) -> tuple[str, str]`

Comprime un archivo SKILL.md y opcionalmente lo guarda.

### `get\_compression\_ratio(content: str) -> float`

Return compression ratio for content (0.0 = no compression, 1.0 = fully compressed).

### `get\_stats() -> dict[str, Any]`

Return minifier statistics.

### `minify\_all\_skills(skills\_dir: str = '.opencode/skills', dry\_run: bool = True) -> dict[str, Any]`

Minifica todos los SKILL.md en un directorio de skills.
