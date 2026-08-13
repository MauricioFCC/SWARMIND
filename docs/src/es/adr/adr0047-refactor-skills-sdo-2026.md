# ADR-0047: Refactor Skills 2026 — SDO + session-start hook (frontier repos)

> **Estado:** Aprobado (2026-08-13)
> **Fecha:** 2026-08-13

## Contexto

Investigación web de frontera sobre repos de skills en GitHub para pulir los
33 skills de SWARMIND. Dos fuentes principales analizadas en profundidad:

1. **`anthropics/skills`** (169k⭐) — repo oficial Agent Skills (Linux
   Foundation). Patrones: tabla de decisión `Task|Approach`, scripts caja
   negra (`--help` primero, no leer source), salida JSON parseable,
   auto-repair, anti-triggers, evals baseline con/sin skill.
2. **`obra/superpowers`** (272k⭐ — el repo de skills más popular del mundo).
   Joya: **SDO — Skill Discovery Optimization** con evidencia empírica:
   - La `description` debe ser **SOLO condiciones de disparo** ("Use when...").
   - **NUNCA resumir el workflow** del skill en la description: el agente
     sigue la description y se salta el cuerpo del skill (evidencia
     documentada).
   - **Session-start hook** (AGENTS.md inyecta metodología al inicio).
   - **REQUIRED SUB-SKILL / REQUIRED BACKGROUND**: composición explícita entre
     skills, prohibido usar `@` links (cargan 200k+ tokens).
   - Eficiencia de tokens: get-started <150 palabras, frecuentes <200, resto
     <500; delegar flags a `--help`.
   - Iron Law: "NO SKILL WITHOUT A FAILING TEST FIRST".

## Decisión

### 1. AGENTS.md (session-start hook) — CREADO

`AGENTS.md` en la raíz del repo: inyecta la doctrina (RSF/IDP/ERR/ARQ/SEG/DOC/
TST/CMT/TKN/AGR/UPG/FRS) + cómo trabajar (investigar, validar skills,
ADRs locales, docs oficiales, tests 4414, commits, push-guard). Es el patrón
"instrucciones iniciales + skills componibles" de superpowers.

### 2. Refactor SDO de las 33 descripciones — APLICADO

Todas las `description` (SKILL.md + SKILL.min.md + registry) reescritas al
patrón:

```
Usar cuando <condicion de disparo>. <keywords de sintoma>. | UPG·NAM·FRS (...)
```

Ejemplo (data-science):
`"Usar cuando el usuario trabaja con datos, ML o pipelines. pandas, numpy,
scikit-learn, pytorch, feature engineering, model evaluation, GPU, analisis
de datos | UPG·NAM·FRS (reglas en base_principles.md)"`

Antes era un resumen de workflow ("Experto en Data Science y ML: pandas,
numpy...") — exactamente lo que SDO prohíbe.

### 3. Validador actualizado con regla SDO

`scripts/validate_skills.py` ahora exige que la description **empiece** con
"Usar cuando" (error en strict si no), junto a las reglas existentes
(frontmatter, min.md, registry, referencias, tamaño).

### 4. Composición explícita REQUIRED SUB-SKILL — APLICADO (2 skills)

- `responsive-ui` → `frontend-uiux` (dependencia real, composición UI).
- `swarm-release-ops` → `devops-infra` (CI genérico + específico SWARMIND).

### 5. Salida JSON en self_check.py — APLICADO

`diagram-design/scripts/self_check.py` ahora soporta `--json` con salida
parseable `{status, files:[{file, status, errors}]}` (patrón frontier).

## Consecuencias

### Positivas
- **Mejor activación**: las descripciones SDO hacen que el router de skills
  dispare con precisión (los agentes infra-disparan sin condiciones claras).
- **Menos falsos positivos**: el agente ya no sigue el resumen del workflow en
  la description (saltándose el body).
- **Composición explícita**: el agente sabe qué skills combinar.
- **AGENTS.md** inyecta doctrina en cada sesión (también útil para forks).

### Negativas
- Las descripciones son más largas (más tokens en el escaneo de metadata
  ~100 tokens por skill × 33 ≈ 3.3k tokens al arranque — aceptable).
- El validador ahora es estricto en SDO: skills nuevos deben cumplir el
  patrón desde el inicio.

## Alternativas consideradas

1. **Adoptar superpowers completo** — RECHAZADO: es un framework de
   metodología (14 skills), duplica el orchestrator y los principios N1/N2 de
   SWARMIND. Solo se extrajeron los patrones (SDO, hooks, composición).
2. **Solo documentar, sin refactor** — RECHAZADO: la evidencia empírica de
   superpowers (descripción-workflow → agente salta el body) justifica el
   cambio inmediato.
3. **Refactor SDO + validador + composición** — ACEPTADO (KISS, impacto
   directo en activación).

## Commit

- `SKILL` — AGENTS.md, 33 descripciones SDO (SKILL.md + min.md + registry),
  validador con regla SDO, REQUIRED SUB-SKILL ×2, self_check --json.
