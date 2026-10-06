---
name: skill-engineering
domain: meta
version: 1.0.0
project_agnostic: true
license: MIT
description: "Usar cuando el usuario quiere crear, revisar, mejorar o auditar skills o agentes del harness. skill engineering, frontmatter, description pushy, progressive disclosure, routing, evaluacion, lifecycle, drift. Alcance: mejora de skills; para mejora del sistema ver evolve. | UPG·NAM·FRS (reglas en base_principles.md)"
---

# Skill Engineering (min)

La `description` es el router; el `SKILL.md` es el contrato; el body es el
detalle progresivo. Mejora = ciclo reflexivo GEPA: generar → evaluar (Skill
Lift paired) → promover sólo con lift > 0 y validate verde.

## Canon
- Anthropic Agent Skills spec + best practices
- DSPy GEPA (reflective prompt evolution)
- SkillRouter (body-aware routing at scale)
- SkillsBench (paired Skill Lift; narrow skills 2-3 módulos)

## Checklist frontera (10)
1. Frontmatter válido (name/description obligatorios; license/compatibility/metadata opcionales)
2. `description` = ÚNICO disparador: qué + CUÁNDO + keywords + cuándo NO usar (abre con "Usar cuando")
3. Progressive disclosure: SKILL.md <500 líneas / <5k tokens; detalle en references/scripts/assets
4. Cuerpo = contrato: entradas, pasos, criterios VERIFICABLES, errores, anti-patrones
5. Anti-bloat: 2-3 módulos enfocados; si el nombre necesita "and/or", dividir
6. Routing: medir precisión/recall de selección; anti-triggers documentados
7. Composición: depende/conflicta/especializa/duplica + detección de ciclos
8. Evaluación paired: Skill Lift (no-skill vs curated vs self-generated), pass@k, tareas negativas
9. Lifecycle: semver, conflict detection, deprecación, rollback; no publicar autogenerada sin validar
10. Drift: dedup semántico, fingerprint por componentes, detección de novedad

## Comandos
- `validate_skills.py --strict` (gate) · `audit_skills_agents.py [--json|--fix]` (checklist) · `!skill load <name>`

## Anti-patrones
- Reescribir bodies sin spec ni evidencia · description que resume el workflow
- Inventar anti-triggers · publicar autogenerada sin validar · duplicar en vez de especializar
