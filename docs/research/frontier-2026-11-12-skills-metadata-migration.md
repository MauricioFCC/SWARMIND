# Frontier research — Migración de frontmatter de skills a `metadata` (expand/contract)

> **Fecha:** 2026-11-12 · **Ciclo:** 11.96 · **Skill:** `frontier-engineering`
> **Tarea explícita:** migrar masivamente `domain`, `version` y
> `project_agnostic` de nivel superior a `metadata:` (mapa string→string de la
> spec Agent Skills), sin romper `inherit`/`variables`/`invocation`/`calls`
> (estructuras que el estándar aún no define).

## 1. Fuentes leídas

| # | Fuente | URL | Aporte | Estado |
|---|--------|-----|--------|--------|
| F1 | Agent Skills — Specification | https://agentskills.io/specification.md | `metadata` = mapa string→string; `name`/`description`/`license`/`compatibility`/`allowed-tools` | ✅ leída |
| F2 | Agent Skills — Best practices | https://agentskills.io/skill-creation/best-practices.md | contexto justo, progressive disclosure, calibración | ✅ leída |
| F3 | Anthropic — *Donating Agent Skills to AAIF* (2026-10-22) | https://www.anthropic.com/news/donating-agent-skills-to-the-agentic-ai-foundation | estándar vendor-neutral; releases versionadas y security guidance | ✅ leída |
| F4 | Semantic Versioning 2.0.0 | https://semver.org/ | `version` es `X.Y.Z` (string), no número | ✅ leída |
| F5 | Martin Fowler — *Parallel Change* (expand/contract) | https://martinfowler.com/bliki/ParallelChange.html | migrar interfaces en 3 fases: expandir, migrar, contraer | ✅ leída |
| F6 | JSON Schema — Object | https://json-schema.org/understanding-json-schema/reference/object | claves string; `properties`/`patternProperties`; valores tipados | ✅ leída |
| F7 | FR-0009 (notas de research, 2026-11-11) — *Agent = LLM + arnés* | `local://FRONTIER_RESEARCH/FR-0009-11NOV2026-Articulos-varios-linkeding.md` | El arnés (contexto, herramientas, runtime, interfaz) consume el frontmatter; la skill es el contrato portable | ✅ leída |
| F8 | benjitaylor/skills (Stageshow) | https://github.com/benjitaylor/skills | Skill real que graba el resultado para que el agente se autorevise; ejemplo de skill con recursos | ✅ verificada |
| F9 | cloudflare/security-audit-skill | https://github.com/cloudflare/security-audit-skill | Auditoría de seguridad multifase con hallazgos verificables y machine-readable | ✅ verificada |
| F10 | FR-0009 — panorama de orquestación (CrewAI, Microsoft Agent Framework, OpenAI Agents SDK, Google ADK, Claude Agent SDK) | `local://FRONTIER_RESEARCH/FR-0009-11NOV2026-Articulos-varios-linkeding.md` | `calls`/`invocation` son primitivas de composición; el estándar aún no las define (extensión) | ✅ leída |

## 1.1 Aportes de FR-0009 (2026-11-11)

- **Agente = LLM + arnés** (contexto, herramientas, runtime, interfaz): el
  frontmatter es el contrato que viaja entre OpenCode, Claude Code y Codex; la
  migración debe ser vendor-neutral y no depender de un loader concreto.
- **`benjitaylor/skills` (Stageshow)**: skill real que graba su propia demo y
  devuelve el resultado al agente para autoevaluación. Refuerza el uso de
  `scripts/`/`assets/` y del `SKILL.spec.json` como contrato verificable.
- **`cloudflare/security-audit-skill`**: auditoría de seguridad multifase con
  hallazgos verificables y machine-readable; referencia para nuestro
  `security-audit`/`mcp-security` y para la security guidance del roadmap AAIF.
- **Panorama de orquestación** (CrewAI, Microsoft Agent Framework, OpenAI
  Agents SDK, Google ADK, Claude Agent SDK): confirma que `calls`/`invocation`
  son primitivas reales de composición que el estándar aún no cubre; se
  mantienen como extensión documentada.
- **No adoptado**: afirmaciones especulativas del boletín (p. ej. “1.000
  agentes formalizan Fermat” o modelos no verificados) quedan como
  `[UNVERIFIED]` y no influyen en la decisión técnica.

## 2. Hipótesis comparadas

Criterios: **C** = conformidad con la spec; **R** = compatibilidad hacia atrás;
**L** = latencia de parseo; **E** = escalabilidad (50→1000 skills); **B** =
robustez/rollback; **P** = reproducibilidad.

| Hipótesis | C | R | L | E | B | P | Veredicto |
|-----------|---|---|---|---|---|---|-----------|
| **H1. Big-bang** (borrar top-level y cambiar todo de golpe) | Alta | Baja | Alta | Alta | Baja | Media | Riesgo de romper consumidores/rollback |
| **H2. Expand/contract** (metadata + parsers dual-read → migrar → contraer) | **Alta** | **Alta** | **Alta** | **Alta** | **Alta** | **Alta** | **Elegida** |
| H3. Sidecar `skill.yaml` (dejar SKILL.md intacto) | Baja | Alta | Media | Media | Alta | Alta | Duplica la fuente de verdad |
| H4. Serializar extensiones como JSON string en `metadata` | Alta | Media | Baja | Media | Media | Media | Ilegible para humanos |

**Decisión:** H2. Como controlamos todos los consumidores (validadores,
auditor, generador de specs, registry), la fase *contract* se ejecuta en la
misma iteración para los 3 campos escalares; el fallback dual-read se conserva
para skills de terceros.

## 3. Gap analysis (IDP)

Lo que ya existe:

- `validate_skills.py` y `audit_skills_agents.py` exigen `version` y
  `project_agnostic` **top-level** con parsers naive (no leen `metadata`).
- `generate_skill_specs.py` usa YAML y lee `front.get("version")` top-level.
- `skill_schema.json` requiere `version` top-level.
- `inherit`/`variables`/`invocation`/`calls` los consumen `skill_inherit.py` y
  `skill_composition.py`; son listas/mapas, no strings.
- El `metadata` actual de muchas skills es **rico** (`input_schema`,
  `output_schema`, `tags` como lista): no cumple string→string.

Gaps que cierra esta iteración:

1. Migrador determinista e idempotente (no manual, no LLM).
2. Parsers dual-read (metadata primero, top-level como fallback).
3. Contrato SDD y tests adversarios (idempotencia, preservación de body y de
   `inherit`/`variables`/`calls`).
4. Schema/spec del repo alineados.

**Fuera de alcance (segunda ola):** mover `input_schema`/`output_schema`/`tags`
a `SKILL.spec.json`; requiere una spec de composición que el estándar aún no
define. Se documenta con su motivo.

## 4. Diseño y complejidad

```
SKILL.md (legacy)                     SKILL.md (migrado)
---                                   ---
name: x                               name: x
domain: education          ──▶        description: ...
version: 1.0.0                        license: MIT
project_agnostic: true                compatibility: ...
inherit: [...]                        inherit: [...]        # extensión
variables: [...]                      variables: [...]      # extensión
metadata: { ...rico... }              metadata:
                                        ...rico...
                                        domain: "education"
                                        version: "1.0.0"
                                        project_agnostic: "true"
---                                   ---
```

- `migrate_frontmatter(text) -> (text, changed)`: parser de líneas que aísla
  bloques top-level, mueve los 3 escalares y preserva el resto byte a byte.
- Complejidad: `O(F)` por skill (F = líneas de frontmatter), total
  `O(S·F)` con S=50; sin `O(n²)`.
- Parseo dual-read: `O(1)` por clave (dict de metadata + fallback top-level).
- Antes: edición manual `O(S·F)` con riesgo de drift; después: script
  determinista e idempotente.

## 5. Riesgos y mitigaciones

- **Romper consumidores**: dual-read + tests de layout legacy.
- **Perder estructura** (`inherit`/`variables`): el migrador solo toca los 3
  bloques; test que compara el resto del frontmatter y el body.
- **Drift de specs/registry**: `generate_skill_specs --write` y
  `hash_skills_registry --write` tras migrar; gates `skills`/`skills-standard`/
  `skills-spec`.
- **Metadata rica no conforme**: se declara segunda ola; no se finge que ya
  cumple string→string.

## 6. No aplicado (con motivo)

- **Migrar `input_schema`/`output_schema`/`tags`**: el estándar define
  `metadata` como string→string; moverlos a `SKILL.spec.json` es correcto pero
  requiere decide el contrato de composición (aún no definido por AAIF).
- **Eliminar el fallback top-level**: se conserva para skills de terceros;
  las 50 del repo quedan migradas.
- **Migración automática de `inherit`/`variables`/`invocation`/`calls`**: no
  son strings y no tienen campo oficial; se mantienen como extensión
  documentada.
