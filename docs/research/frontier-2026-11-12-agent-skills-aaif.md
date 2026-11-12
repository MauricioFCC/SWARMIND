# Frontier research — Agent Skills estándar (AAIF) aplicado a SWARMIND

> **Fecha:** 2026-11-12 · **Ciclo:** 11.95 · **Skill:** `skill-engineering`
> **Tarea explícita:** revisar `agentskills.io` y la donación del estándar a la
> Agentic AI Foundation para mejorar el sistema de skills del harness.

## 1. Fuentes leídas

| # | Fuente | URL | Aporte | Estado |
|---|--------|-----|--------|--------|
| F1 | Agent Skills — Overview | https://agentskills.io/home | Skill = carpeta con `SKILL.md` + `scripts/`/`references/`/`assets/`; progressive disclosure | ✅ leída |
| F2 | Agent Skills — Specification | https://agentskills.io/specification.md | Campos oficiales, límites y `metadata` string→string | ✅ leída |
| F3 | Agent Skills — Best practices | https://agentskills.io/skill-creation/best-practices.md | Expertise real, ejecución real, contexto justo, calibración | ✅ leída |
| F4 | Anthropic — *Donating Agent Skills to the Agentic AI Foundation* (2026-10-22) | https://www.anthropic.com/news/donating-agent-skills-to-the-agentic-ai-foundation | 70+ plataformas, 1M skills, 280M instalaciones; gobernanza neutral (Linux Foundation) | ✅ leída |

## 2. Hallazgos

- **Formato:** `name` (1-64, `[a-z0-9-]`, == directorio), `description`
  (1-1024), `license`, `compatibility` (≤500), `metadata` (mapa string→string),
  `allowed-tools` (experimental). `SKILL.md` <500 líneas / <5k tokens.
- **Progressive disclosure:** discovery (solo name+description) → activation
  (`SKILL.md`) → execution (`references/`/`scripts/` bajo demanda).
- **Gobernanza:** el estándar ya es vendor-neutral (AAIF/Linux Foundation); no
  hay lock-in. Roadmap: releases versionadas, proposal process y **security
  guidance** para autores/instaladores.
- **Calidad:** las skills nacen de experiencia real y se refinan ejecutándolas;
  las instrucciones deben ser específicas del proyecto, no genéricas.

## 3. Gap analysis (IDP)

Lo que SWARMIND ya tenía:

- 49 skills con `SKILL.md` + `SKILL.min.md` + registry con `sha256`.
- `validate_skills --strict` (min.md, registry, referencias, tokens).
- `SkillFrontmatterValidator` (L1 oficial) ya implementado en
  `harness/memory_rag/skill_frontmatter.py`, **pero no cableado** a un gate.
- `generate_skill_specs.py` (contratos SDD) y `audit_skills_agents.py`.

Gaps cerrados en este ciclo:

1. **Gate de conformidad oficial**: `check_skills_standard.py` valida L1 con el
   validador existente; entra en `xtask` como `skills-standard`.
2. **Gate de contratos SDD**: `generate_skill_specs.py --check` como
   `skills-spec` (detecta drift de `source_sha256`).
3. **Skill de referencia**: `socratic-tutor` con `compatibility`, PEC,
   `SKILL.spec.json` y mappings de router/agente.
4. **Documentación del estándar** (`docs/skills/AGENT_SKILLS_STANDARD.md`) y
   regla para skills nuevas: layout oficial + `SKILL.spec.json`.

## 4. Hipótesis y decisión

| Hipótesis | Conformidad | Riesgo | Costo | Veredicto |
|---|---|---|---|---|
| H1. Solo nuestro validador | Media | Bajo | Bajo | Insuficiente: no detecta regresiones L1 |
| **H2. Gate oficial + extensiones documentadas** | **Alta** | **Bajo** | Bajo | **Elegida** |
| H3. Migrar todo a `metadata` string y eliminar extensiones | Muy alta | Alto (rompe `inherit`/`variables`/`calls`) | Alto | Diferida |

**Decisión:** H2. Los campos `domain`/`version`/`project_agnostic`/`inherit`/
`variables`/`invocation`/`calls` se mantienen como extensión documentada; las
skills nuevas usan el layout oficial + `SKILL.spec.json`. La migración completa
(H3) requiere una spec de composición que el estándar aún no define.

## 5. Evidencia

- `check_skills_standard.py` → **50/50 conformes** (L1).
- `generate_skill_specs.py --check` → **50 specs al día**.
- `validate_skills.py --strict` → **50 skills válidos**.
- `pytest test_skill_pec.py test_skill_router_registry_sync.py
  test_validate_skills.py test_skill_overlap.py` → **293 passed**.

## 6. No aplicado (con motivo)

- Migración masiva a `metadata` string→string: `inherit`/`variables`/`calls`
  son estructuras que el estándar no define; forzarlas a strings rompería la
  composición. Se documenta el path y se aplica a skills nuevas.
- `allowed-tools`: experimental; no se usa como barrera de seguridad.
- Evaluación paired (Skill Lift) por skill: existe `skill_lift.py`, pero
  requiere tareas por dominio; se deja para el ciclo de evaluación.
