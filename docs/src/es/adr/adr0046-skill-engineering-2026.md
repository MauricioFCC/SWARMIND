# ADR-0046: Skill Engineering 2026 (spec Anthropic + diagram-design)

> **Estado:** Aprobado (2026-08-13)
> **Fecha:** 2026-08-13

## Contexto

Investigación de frontera para mejorar skills y agentes del proyecto, a partir
de dos fuentes:

1. **`anthropics/skills`** (169k⭐) — repo oficial de Agent Skills; especificación
   en `agentskills.io/specification` + plantilla oficial + skills de ejemplo.
2. **`cathrynlavery/diagram-design`** (14.3k⭐) — skill de diagramas editoriales
   para Claude Code (adoptado en ADR-0045), con patrones avanzados de diseño
   de skills.

## Hallazgos de la mesa (investigación web frontier 2026-08-13)

### De la spec oficial Anthropic
- **Frontmatter obligatorio**: `name` (≤64 chars, minúsculas/dígitos/hífens,
  coincide con el directorio) + `description` (≤1024 chars, con **keywords de
  disparo** — los agentes tienden a infra-disparar sin triggers explícitos).
- **Progressive disclosure en 3 niveles**: metadata (~100 tokens, todas las
  skills) → instrucciones (<5000 tokens, SKILL.md al activarse) → recursos
  bajo demanda (`references/`, `scripts/`, `assets/`).
- **Tamaño recomendado**: SKILL.md <500 líneas; material detallado a
  references con punteros claros.
- **Validación**: `skills-ref validate` (frontmatter + naming).
- **Evals empíricos**: 2-3 prompts de test, baseline con/sin skill,
  pass_rate/tokens/timing, iteración con feedback humano.

### Del skill diagram-design
- **Description "trigger-rich"** forzada por CI (nombra los 27 tipos como
  disparadores léxicos).
- **Gate de primera vez** que pausa y pregunta (style-guide) antes del primer
  uso.
- **Self-check empaquetado** (`self_check.py`, sin dependencias, viaja con el
  skill) para que el agente auto-valide su output.
- **ADRs propios** del skill documentando decisiones de diseño.
- **"Redraw, never convert"** + fidelity ledger: descarta el renderer original
  (draw.io/Mermaid) y reporta qué cortó/fusionó.
- **Presupuestos numéricos por tipo + presets** que escalan el type ramp.

## Decisión

1. **Crear `scripts/validate_skills.py`** — validador de skills según la spec
   Anthropic + convenciones SWARMIND:
   - frontmatter obligatorio (name/description/version/project_agnostic)
   - name coincide con directorio y formato spec
   - description con keyword de disparo (warning si falta)
   - SKILL.min.md presente (convención SWARMIND de progressive disclosure)
   - SKILL.md <500 líneas (warning)
   - referencias existentes (rutas no rotas)
   - registry sincronizado con el directorio
   - `--strict` para CI (exit code != 0 si errores)

2. **Corregir gaps detectados por el validador**:
   - `alpha-research`, `quant-trading`, `risk-execution`: faltaba
     `version` + `project_agnostic` en frontmatter.
   - `swarm-release-ops`: faltaba `project_agnostic` + `SKILL.min.md` (creado).
   - Registry: faltaban `ads-optimizer` y `swarm-release-ops` (añadidos).

3. **Potenciar 7 descripciones** con trigger keywords (spec "pushy"):
   `architecture`, `business-strategy`, `creative-design`, `evolve`,
   `math-doc`, `responsive-ui`, `science-doc` — patrón
   "Qué hace + **Usar con:** <triggers>".

4. **No implementar evals baseline** en este ADR (YAGNI): el harness ya tiene
   `harness/evals/`; la mejora de evals de skills se difiere a cuando haya un
   skill con evaluaciones cuantitativas reales (el patrón Anthropic exige
   prompts de test + baseline medible, no aplicable a todos los skills).

## Consecuencias

### Positivas
- **33 skills validados** con frontmatter completo, min.md y registry sincronizado.
- Descripciones con triggers → mejor disparo del router de skills (los agentes
  infra-disparan sin keywords explícitas).
- Validador CI-ready (`--strict`) — gate de calidad en pre-commit futuro.
- Patrón progressive disclosure reforzado (SKILL.md corto + references bajo demanda).

### Negativas
- `frontend-uiux` (682 líneas) y `diagram-design` (573) exceden el límite
  recomendado de 500 — aceptado: ambos usan references/ para progressive
  disclosure y su cuerpo principal es la instrucción completa.
- Los warnings de tamaño requieren decisión humana, no auto-acción (no romper
  skills funcionales por un límite numérico — YAGNI).

## Alternativas consideradas

1. **Reescribir todos los skills <500 líneas** — RECHAZADO: riesgo alto,
   pérdida de contexto, viola YAGNI (los warnings no son errores).
2. **Integrar `skills-ref` de Anthropic como CLI** — RECHAZADO: es Node.js,
   añade dependencia; el validador propio es 100% Python stdlib, portable.
3. **Validador propio + correcciones quirúrgicas** — ACEPTADO.

## Commit

- `SKILL` — `scripts/validate_skills.py`, 4 frontmatters corregidos,
  7 descripciones potenciadas, `SKILL.min.md` de swarm-release-ops,
  registry 31→33.
