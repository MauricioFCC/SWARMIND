---
name: evolve
description: "Usar cuando el usuario quiere mejorar el sistema o sus skills. auto-mejora, evolucion, ASI-Evolve, aprendizaje continuo, mejora de skills, FDE, meta-aprendizaje. Alcance: mejora del sistema y sus skills; para disciplina pre-merge ver agent-rigor. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
---

# Evolve (min)

Meta-skill del loop **ASI-Evolve** (Learn → Design → Experiment → Analyze): mejora skills, agentes y configs con FDE, Cognition Store (lecciones) y Experiment DB (scores).

## Aterrizaje (motor real)
Los comandos `!evolve ...` corren sobre `harness.evolve_loop` (API pública `CASEEvaluator, SelfImprover, ProceduralMemory, CognitionSync, SkillGenerator`).

## Comandos esenciales
- `!evolve run <skill-path> [rounds=10] [sample_n=3]` / `!evolve run all`
- `!evolve cognition add|search|list|seed`
- `!evolve best|history|compare`
- `!evolve fde audit <skill-path>` · `!evolve failures distill`

## FDE por ronda
DELTA (gap) · MISSION (score medible) · GLUE (portable) · VALUE (80/20) · DIPLOMACY (compatibilidad) · RESILIENCE (guardrails) · EVOLVE (meta-loop).

## Guardrails
Sin registro no hay mutación · `max_rounds` con reporte intermedio · preservar `project_agnostic: true` · compatibilidad hacia atrás · siempre registrar lección.

## Checklist
- [ ] Delta real (FDE) · Hipótesis con métrica · Registro en Experiment DB
- [ ] Lección en Cognition Store · Rollback si lift <= 0 · `validate_skills --strict`

## Referencias (bajo demanda)
- [Comandos](references/comandos.md) · [Frameworks 2026](references/frameworks-2026.md) · [Métricas y FDE](references/metricas-y-fde.md)
