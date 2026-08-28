# ADR-0043: Refactor de Deuda AGR a Paquetes

> **Estado:** Aprobado (2026-08-11)
> **Fecha:** 2026-08-11

## Contexto

El harness tenía 32 módulos planos con más de 500 líneas cada uno (algunos hasta
905 líneas): `factory.py` 905, `federated_search.py` 865, `adaptive_planner.py`
859, `debate_orchestrator.py` 856, `sqlite_vec_adapter.py` 837, `metaclaw.py` 833,
`worktable.py` 829, `scheduler.py` 811, `agent_kpi_tracker.py` 804,
`mars_scheduler.py` 1141.

La regla AGR (máximo <500 líneas/archivo) los marcaba como deuda técnica, y el
Bug Hunting pre-commit los señalaba en cada gate.

## Decisión

1. **Convertir los 32 módulos planos a paquetes** con `__init__.py`
   re-exportador de TODOS los símbolos públicos + submódulos cohesivos
   (`core.py`, `models.py`, `constants.py`, `mixins`).
2. **Dividir clases grandes en mixins** con MÁXIMO 2 bases custom (SOL:
   herencia ≤2). Corrección de SOL en 9 clases: `AIFactory`, `GuardrailEngine`,
   `ContextAssembler`, `FederatedVectorSearch`, `SQLiteVecAdapter`, `AgentBus`,
   `MultiUserGovernance`, `OrganizationalLayer`, `ToolGuardian`.
3. **Lookup dinámico `_rc.`** en `run_commands/`: `import harness.run_commands
   as _rc` + llamadas `_rc.logger`, etc., para que los patches de tests sigan
   funcionando.
4. **`run_commands` dividido** en `colors.py` + `handlers_iteration.py` +
   `handlers_other.py` + `handlers_extra.py`.
5. **`run.py` dividido** en `run.py` (445 líneas) + `run_support.py`.

## Consecuencias

### Positivas
- 0 archivos >500 líneas en código no-test.
- Ruff All checks passed; Vulture 0.
- Suite completa: 4414 passed / 37 skipped / 4 xfailed sin regresiones.
- Imports backward-compat verificados (rutas originales idénticas).
- `test_universal_rules` verde.

### Negativas
- Mayor número de archivos: navegar requiere conocer la estructura de paquetes.
- Curva de aprendizaje para contribuidores.

## Alternativas consideradas

1. **Scripts de transformación automática** — RECHAZADO: un script de fusión de
   mixins (`fuse_mixins.py`) rompió docstrings y dejó paréntesis dobles.
2. **Dejar la deuda y añadir excepciones al Bug Hunting** — RECHAZADO (contra el
   principio deuda cero).
3. **Mover solo módulos críticos** — RECHAZADO (incompleto).

## Pendiente documentado

- Funciones >30 líneas (guideline FSZ, no gate): diferido deliberadamente para no
  arriesgar los oráculos de validación PBT/mutation.

## Commits

- `e409982` — refactor de 19 módulos.
- `545e591` — refactor de 13 módulos final.
- `a1624ee` — eliminación del artefacto `x.json`.
