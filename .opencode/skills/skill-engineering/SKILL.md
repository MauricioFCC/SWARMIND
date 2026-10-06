---
name: skill-engineering
domain: meta
version: 1.0.0
project_agnostic: true
license: MIT
compatibility: 'Python 3.12+; SWARMIND harness (scripts/validate_skills.py, scripts/audit_skills_agents.py)'
description: "Usar cuando el usuario quiere crear, revisar, mejorar o auditar skills o agentes del harness. skill engineering, frontmatter, description pushy, progressive disclosure, routing, evaluacion, lifecycle, drift. Alcance: mejora de skills; para mejora del sistema ver evolve. | UPG·NAM·FRS (reglas en base_principles.md)"
inherit:
  - core/base_principles.md
---

# Skill Engineering | Como mejorar y usar skills/agentes

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **ingeniero/a de harness senior (10+ años) experto en
  Agent Skills: la `description` es el router, el `SKILL.md` es el contrato, el
  body es el detalle progressivo. No publicas una skill sin evidencia de Skill Lift.**
- **CANON** (estudiar ANTES de generar, regla RSF):
  - Anthropic — Agent Skills spec + authoring best practices — https://agentskills.io/specification
  - DSPy **GEPA** — Reflective Prompt Evolution — https://arxiv.org/abs/2507.19457
  - **SkillRouter** — body-aware routing at scale — https://arxiv.org/abs/2603.22455
  - **SkillsBench** — paired skill-lift benchmark — https://arxiv.org/abs/2602.12670
- **ANTI-HEDGING**: toda mejora se cierra con un check ejecutable y su
  evidencia (validate + audit + Skill Lift). Sin evidencia = sin merge.

## Descripción — tesis de frontera

Una skill NO es un prompt largo: es un **componente descubrible y evaluable**.
El descubrimiento ocurre en la metadata (`name` + `description`), la ejecución
consume el `SKILL.md`, y el detalle pesado se carga sólo bajo demanda
(progressive disclosure). En registries grandes, ocultar el cuerpo cuesta
31-44pp de routing accuracy (SkillRouter 2026); la `description` debe ser
**pushy** (qué hace + CUÁNDO usarla + keywords + cuándo NO), porque es el
único disparador. La mejora de una skill es un ciclo **reflexivo** (GEPA):
generar → evaluar con feedback textual → refinar la variante Pareto-óptima,
no un reescrito a ciegas.

## Comandos

- `.venv\Scripts\python.exe scripts\validate_skills.py --strict` — gate de
  frontmatter/min.md/registry/referencias (spec Agent Skills 2026).
- `.venv\Scripts\python.exe scripts\audit_skills_agents.py` — auditoría del
  checklist; `--json` para CI; `--fix` para normalizar frontmatter seguro.
- Cargar una skill: `!skill load <name>` (descubre por `description`).

## Checklist frontera para mejorar una skill/agente

- [ ] **Frontmatter válido**: `name` y `description` obligatorios; `license`,
  `compatibility`, `metadata` opcionales recomendados. `name` == directorio,
  minúsculas/dígitos/guiones.
- [ ] **`description` = ÚNICO disparador**: qué hace + CUÁNDO usarla + keywords
  de disparo + **cuándo NO usar** (anti-triggers explícitos). Debe abrir con
  "Usar cuando".
- [ ] **Progressive disclosure**: `SKILL.md` <500 líneas / <5k tokens; el
  detalle va en `references/`, `scripts/`, `assets/`; referencias a UN SOLO
  nivel.
- [ ] **Cuerpo como contrato**: entradas, pasos, **criterios de éxito
  verificables**, errores comunes y anti-patrones (no prosa aspiracional).
- [ ] **Anti instruction-bloat**: 2-3 módulos enfocados; si el nombre necesita
  "and"/"or", fusionar o dividir (una responsabilidad).
- [ ] **Routing explícito**: exponer `name`+`description` a un router;
  documentar anti-triggers; medir precisión/recall de selección (entre skills
  solapadas).
- [ ] **Composición declarada**: dependencias/conflictos (depende/conflicta/
  especializa/duplica) y detección de ciclos antes de publicar.
- [ ] **Evaluación paired y determinista**: Skill Lift (no-skill vs curated vs
  self-generated), `pass@k`, tareas negativas; nunca "se ve mejor".
- [ ] **Lifecycle/governance**: versionado semántico, conflict detection,
  deprecación y rollback; nunca publicar una skill autogenerada sin validar.
- [ ] **Drift**: dedup por similitud semántica, fingerprint por componentes,
  detección de novedad/obsolescencia en cada ciclo de evolución.

## Flujo de mejora (EVO + GEPA)

1. **Diagnosticar**: correr `audit_skills_agents.py` y leer WARN/FAIL.
2. **Proponer**: una variante por hallazgo (no reescribir todo).
3. **Evaluar**: paired test no-skill vs variante (Skill Lift, pass@k).
4. **Promover** solo si `validate_skills.py --strict` pasa y el lift > 0;
   registrar el delta; si no, rollback.

## Anti-patrones (prohibidos)

- Reescribir el body de otra skill sin spec de mejora ni evidencia.
- `description` que resume el workflow (el agente lo ejecuta y salta el body).
- Inventar anti-triggers o prometer cobertura no verificada.
- Publicar skill autogenerada sin `validate_skills.py` ni evaluación paired.
- Duplicar una skill existente en vez de especializarla (rompe routing).

## Referencias

- `.opencode/skills/skills_registry.yaml` (registro SSOT de skills).
- `scripts/validate_skills.py`, `scripts/audit_skills_agents.py`.
- `harness/context/skill_contract.py` (contratos SDD, ADR-0048).
- `core/base_principles.md` (RSF, VER, TST, FRS, EVO).

## Agentes que lo usan

- `evolve`, `evolve-engineer`, `evolve-analyzer`, `evolve-researcher`,
  `architect`, `guardian` (`.opencode/agents/`).
