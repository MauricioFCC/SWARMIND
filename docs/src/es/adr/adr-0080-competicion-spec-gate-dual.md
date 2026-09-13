# ADR 0080: Competición Aplicada — Spec-Gate Pre-Código + Verificación Dual

## Estado
Aplicado | `harness/validation/{cp_spec_gate,dual_verify}.py` (9 tests) | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
CP moderno (arXiv 2506.22954 + Wonda ICML 2026, ya citado en CPD/ADR-0070): el 44% de fallos de LLMs es design (28.6%) + boundary (15.5%) — prevenible con checklist ANTES de codear; y dual verification (solución vs brute-force) confirma corrección sin OJ externo. El principio CPD existía pero sin mecanismo ejecutable en el harness.

## Decisión
1. **`cp_spec_gate.check_spec`**: gate de 4 pilares (`edges`, `invariants`, `complexity`, `io_constraints`); strings blancos y colecciones vacías no cuentan; `TypeError` accionable si no es dict. Sin spec completa = sin start (SPE).
2. **`dual_verify`**: fast vs brute caso por caso; excepción del fast = mismatch (robustez); referencia protegida; reporte frozen (passed, mismatches con índice+obtenido+esperado, conteo).

TDD: 9 tests; ruff 0; vulture 0; mutante `!=`/`==` muerto.

## Consecuencias
### Positivas
- El 44% prevenible se ataca en la puerta (spec), no en repair.
- Verificación sin infraestructura externa (brute-force como oráculo).

### Negativas
- Aún no enchufado en `specs/task_template.md` ni en el guardian (siguiente wiring).

## Alternatives Considered
1. **Solo principio CPD sin mecanismo**: la regla sin gate ejecutable depende de la memoria del modelo (lo que falla).
2. **OJ externo**: infraestructura extra; el brute-force local basta para la mayoría de algoritmos.

## Relacionado
- ADR-0070 (CPD, taxonomía), SPE (spec-first), `specs/task_template.md`
