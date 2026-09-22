# ADR 0100: Dispatch Obligatorio del Coordinador (Determinista vs LLM)

## Estado
Aplicado | `harness/orchestrator/coordinator_dispatch.py` (7 tests) | Propietario: @coordinator | Fecha: 2026-09-22

## Contexto
Research frontera (RedHat Automation 2026.8, Camunda 2026-01): pasos deterministas para lo reglado + LLM solo donde hay interpretacion; schemas JSON enfocados con enums; costos bajo control (input limitado, output constreñido). El coordinador debia OBLIGAR por tarea: agente especializado + skills topadas + backend local-first + contrato de salida.

## Decisión
`dispatch(task, max_skills=3, oracle_sample=False)` retorna `DispatchPlan` frozen:
1. Tarea cerrada (allowlist `is_closed_task`) → path deterministico, agente runner, backend local, 0 tokens cloud.
2. Tarea abierta → `AgentSelector` (con competence si hay) + `SkillBundler` por dominio topado a `max_skills` (minimo 1 skill, fallback `general`) + backend local-first; frontier-only → cloud justificado.
3. Contrato JSON enfocado por defecto + flag `oracle` para muestreo 1%.

TDD: 7 tests; ruff 0; mutante del gate muerto (RC 1).

## Consecuencias
### Positivas
- Cero improvisacion: toda tarea sale con agente+skills+backend+contrato.
- Ahorro estructural: cerradas sin LLM, skills topadas, local-first.

### Negativas
- `_is_frontier_task` por keywords (heuristico; el router de tiers decide en ejecucion).

## Alternatives Considered
1. **LLM para todo**: costo sin control (lo que se evita).
2. **Reglas hardcodeadas por tarea**: fragil; keywords + selector con evidencia.

## Relacionado
- AgentSelector, skill_bundler, LocalExecutor, `local_first` 0.99/0.01, RedHat/Camunda 2026
