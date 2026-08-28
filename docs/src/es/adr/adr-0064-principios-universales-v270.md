# ADR-0064: Principios universales v2.7.0 — SPE/GATE/FAIL/SBX + evolve 3.1.0

**Fecha**: 2026-08-26
**Estado**: Aceptado
**Decisor**: Coordinator (SWARMIND)
**Categoría**: Doctrina / Skill Engineering (SVE)

## Contexto

Los principios universales (N1+N2 de `base_principles.md`) no incluían los 4 patrones de frontera derivados de la investigación 2026:

1. **Proof-or-Stop** (Huang 2026) — spec-first con lifecycle gated por evidencia
2. **Pondero CI-for-Agents** (2026) — 3-tier gates T1/T2/T3
3. **Socratic-SWE** (Qu 2026) — failure traces → skills → tasks
4. **Docker Sandboxes/Cloudflare Workers** (2026) — aislamiento de fallos

Sin estos principios, los agentes no tenían doctrina para: especificar ANTES de ejecutar, gatear por evidencia, registrar fallos estructurados, ni aislar ejecución.

## Decisión

### 1. base_principles.md v2.6.0 → v2.7.0

Añadir 4 principios al N1 (tokens: +4 líneas, +35 tokens — dentro del budget):

```
SPE: Spec-First (Proof-or-Stop) | spec ANTES de ejecutar | outcome medible | exit criteria definidos | sin spec = sin start
GATE: Evidence-Gated Lifecycle | claim→evidence→gate | 0 false-DONE | T1 deterministic + T2 LLM-judge + T3 regression
FAIL: Failure Registry | registrar fallos en JSONL | distillar en skills | Socratic-SWE traces→tasks | aprender de errores
SBX: Sandboxing | aislamiento de fallos | per-task environment | rollback plan | contenedor o timeout como minimo
```

Y sus descripciones detalladas en N2 (con papers de referencia y métricas de ablation).

### 2. evolve skill v3.0.0 → v3.1.0

Integrar la doctrina al meta-skill:
- Sección "Failure Registry (Socratic-SWE)" con 5 comandos nuevos (`!evolve failures recent/stats/unresolved/skills/distill`)
- Tabla "FRONTIER RESEARCH INTEGRATION" ampliada: +Socratic-SWE, +Proof-or-Stop, +Pondero CI-gates
- El loop ahora consulta `harness/db/failures.jsonl` antes de generar tareas dirigidas

### 3. Alineación SVE

Cambios de versionado acompañan cambios de doctrina (SVE): MAJOR.MINOR en frontmatter de skills/prompts + CHANGELOG.

## Consecuencias

### Positivas
- Agentes especifican antes de ejecutar (SPE) → menos false-DONE
- Outputs gateados por evidencia (GATE) → 0 afirmaciones sin verificación
- Fallos registrados estructuradamente (FAIL) → evolve loop aprende
- Ejecución aislable (SBX) → fallos contenidos
- Evolve loop mejora con datos reales de fallos

### Negativas
- +35 tokens en N1 (budget: aceptable, sigue <200)
- Skills existentes deben actualizarse para referenciar los nuevos principios (adopción gradual)

### Riesgos
- **Bajo**: SVE versionado, retrocompatible
- **Bajo**: los principios nuevos no invalidan los existentes (son aditivos)

## Referencias

- Huang et al. "Proof-or-Stop" (2026) — [arxiv 2607.14890]
- Qu et al. "Socratic-SWE" (2026) — [alphaxiv 2606.07412]
- Pondero "CI for Agents: Tiered Eval Gates" (2026)
- Docker Sandboxes (2026) + Cloudflare Dynamic Workers (2026)

## Archivos afectados

- `.opencode/core/base_principles.md` (v2.7.0)
- `.opencode/skills/evolve/SKILL.md` (v3.1.0)
- `specs/task_template.md` (creado en ADR-0061)