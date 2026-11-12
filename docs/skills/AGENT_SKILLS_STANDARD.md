# Agent Skills standard (agentskills.io / AAIF)

> **Estándar:** [agentskills.io](https://agentskills.io/home) · donado a la
> [Agentic AI Foundation](https://www.anthropic.com/news/donating-agent-skills-to-the-agentic-ai-foundation)
> (Linux Foundation, 2026-10-22). 70+ plataformas, 1M skills publicadas.
> **Gate:** `python scripts/check_skills_standard.py` (en `xtask`).

## Formato oficial

```
mi-skill/
├── SKILL.md          # obligatorio: frontmatter + instrucciones
├── scripts/          # opcional: código ejecutable
├── references/       # opcional: documentación bajo demanda
├── assets/           # opcional: plantillas/recursos
└── ...
```

`SKILL.md` = YAML frontmatter + Markdown. Campos:

| Campo | Obligatorio | Límite |
|---|---|---|
| `name` | sí | 1-64, `[a-z0-9-]`, sin `--`, == directorio |
| `description` | sí | 1-1024; qué hace + cuándo usarla |
| `license` | no | nombre o archivo |
| `compatibility` | no | ≤500; entorno requerido |
| `metadata` | no | mapa string→string |
| `allowed-tools` | no (experimental) | herramientas pre-aprobadas |

**Progressive disclosure:** al arrancar solo se cargan `name` + `description`;
el `SKILL.md` se activa cuando la tarea coincide; `references/`/`scripts/` se
cargan bajo demanda. Mantener `SKILL.md` <500 líneas y <5k tokens.

## Qué ya cumple SWARMIND

- 50 skills con `SKILL.md` + `SKILL.min.md` + `SKILL.spec.json`.
- `description` pushy con "Usar cuando", keywords y anti-triggers.
- `compatibility` en las skills que lo necesitan.
- Registry SSOT con `sha256` por skill (supply-chain hardening).
- Gate propio `validate_skills --strict` (min.md, registry, referencias).

## Gates nuevos (2026-11-12)

- **`skills-standard`** → `check_skills_standard.py`: valida L1 oficial con
  `SkillFrontmatterValidator` (YAML, `name`, `description`, opcionales).
- **`skills-spec`** → `generate_skill_specs.py --check`: el contrato SDD
  (`SKILL.spec.json`) no tiene drift respecto a `SKILL.md` (`source_sha256`).

## Extensiones SWARMIND (no están en la spec)

`domain`, `version`, `project_agnostic`, `inherit`, `variables`, `invocation`,
`calls` son convenciones del repo. No rompen la spec (los clientes ignoran
campos desconocidos), pero la migración recomendada es:

1. `domain`, `version`, `project_agnostic` → `metadata:` (mapa string→string).
2. Contratos ricos (`input_schema`, `output_schema`, `dependencies`) →
   `SKILL.spec.json` (ya existen para las 50 skills).
3. `inherit`/`variables`/`invocation`/`calls` se quedan como extensión
   documentada hasta que el estándar defina composición.

**Regla para skills nuevas:** usar el layout oficial (`name`, `description`,
`license`, `compatibility`, `metadata` string→string) + `SKILL.spec.json`.
`socratic-tutor` es la implementación de referencia.

## Seguridad (roadmap AAIF)

- Sin secretos ni rutas personales en skills.
- `sha256` en el registry detecta content drift.
- Revisar `scripts/` antes de instalar una skill de terceros.
- `allowed-tools` es experimental: no confiar en él como única barrera.
- El estándar será gobernado por AAIF (releases versionadas, proposal process,
  security guidance); no hay lock-in de Anthropic.
