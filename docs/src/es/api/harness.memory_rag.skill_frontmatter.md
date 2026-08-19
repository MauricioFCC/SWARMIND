<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.skill_frontmatter`

Validador de skills al estandar agentskills.io (progressive disclosure L1).

## `SkillReport`

Resultado inmutable de la validacion de un skill.

### `summary() -> str`

Devuelve una linea legible con el estado del skill.

## `SkillFrontmatterValidator`

Valida archivos y directorios de skills contra agentskills.io L1.

### `validate\_file(skill\_md\_path: str \| Path) -> SkillReport`

Valida un archivo SKILL.md contra el estandar agentskills.io L1.

### `validate\_directory(skill\_dir: str \| Path) -> SkillReport`

Valida el directorio de un skill (SKILL.md + estructura opcional).

### `validate\_all(skills\_root: str \| Path) -> tuple[SkillReport, ...]`

Valida todos los skills bajo ``skills\_root/\*/SKILL.md``.
