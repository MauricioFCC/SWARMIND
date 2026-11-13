# Spec: Migración del frontmatter de skills a `metadata` (expand/contract)

> **Estado:** nueva · **Ciclo:** 11.96 · **Fecha:** 2026-11-12
> **Research:** `docs/research/frontier-2026-11-12-skills-metadata-migration.md`
> **Dueño:** `harness/context/skills_metadata.py` +
> `scripts/migrate_skills_metadata.py` + validadores.
> **Decisión:** H2 (expand/contract): parsers dual-read, migrador determinista,
> `metadata` string→string para los 3 escalares; extensiones no escalares se
> conservan.

## 1. Problema

La spec Agent Skills define `metadata` como un mapa **string→string** y no
define `domain`, `version` ni `project_agnostic` como campos de primer nivel.
Las 50 skills del repo los declaran top-level, así que un cliente estricto
puede ignorarlos o rechazarlos. Migrarlos a mano es propenso a drift.

## 2. Objetivos

1. Migrar `domain`, `version`, `project_agnostic` a `metadata:` como strings.
2. Preservar `inherit`, `variables`, `invocation`, `calls` (extensiones no
   escalares) y el resto del frontmatter/body **byte a byte**.
3. Parsers **dual-read**: leen `metadata.*` y, si falta, el top-level legacy.
4. Migrador **idempotente** y verificable (segunda ejecución = 0 cambios).
5. Actualizar specs SDD y digests del registry.

### No objetivos

- Migrar `input_schema`/`output_schema`/`tags` (metadata rica) — segunda ola.
- Eliminar el fallback top-level para skills de terceros.
- Cambiar el contenido del body o el routing.

## 3. Algoritmo

`migrate_frontmatter(text) -> (text, changed)`:

1. Si no hay frontmatter delimitado por `---`, devolver sin cambios.
2. Aislar bloques top-level (clave + líneas indentadas/continuaciones).
3. Extraer los bloques `domain`, `version`, `project_agnostic` (escalares).
4. Localizar/crear `metadata:` y añadir:
   - `  domain: "<valor>"`
   - `  version: "<valor>"`
   - `  project_agnostic: "true"|"false"`
   (preservando las claves existentes del bloque).
5. Reconstruir sin los 3 bloques top-level; conservar el resto y el body.
6. `changed=False` si ya está migrado (idempotencia).

`migrate_skills(root, write=False) -> report` recorre
`<root>/*/SKILL.md` y `<root>/*/SKILL.min.md`.

Complejidad: `O(F)` por archivo (F = líneas de frontmatter), total `O(S·F)`;
sin `O(n²)`. Parseo dual-read `O(1)` por clave.

## 4. Criterios de aceptación (testeables)

- **AC1** Las 50 skills del repo tienen `metadata.domain`,
  `metadata.version` y `metadata.project_agnostic` como **strings**.
- **AC2** Ninguna skill del repo conserva `domain`/`version`/
  `project_agnostic` top-level.
- **AC3** `inherit`, `variables`, `invocation` y `calls` se preservan
  exactamente (mismo orden y contenido).
- **AC4** El body (después del segundo `---`) queda byte-idéntico.
- **AC5** `migrate_frontmatter` es idempotente: segunda pasada `changed=False`.
- **AC6** Los validadores aceptan el layout legacy y el migrado (fixture legacy
  sigue pasando).
- **AC7** `validate_skills --strict`, `check_skills_standard`,
  `generate_skill_specs --check` y `hash_skills_registry --check` pasan.
- **AC8** Registry y `SKILL.spec.json` quedan sin drift (`source_sha256`).

## 5. Plan TDD (adversario + PBT)

- Unit: mover 3 claves, preservar body, preservar extensiones, metadata
  existente, valores ya citados, `project_agnostic` booleano.
- PBT (hypothesis): para frontmatter aleatorio con/sin metadata, migrar dos
  veces deja el mismo texto y el body intacto; no quedan claves top-level.
- Mutantes esperados: no borrar top-level, no citar `version`, perder
  `inherit`, invertir idempotencia, tocar el body.
- Validadores: parseo de `metadata` anidado + fallback legacy.

## 6. Integración

- `harness/context/skills_metadata.py` (puro) + CLI.
- `validate_skills.py`, `audit_skills_agents.py`, `generate_skill_specs.py`,
  `skill_schema.json` con dual-read.
- `skills_registry.yaml` y `SKILL.spec.json` regenerados.
- ADR en `docs/src/es/adr/` y docs (CHANGELOG/MEJORAS/roadmap).
