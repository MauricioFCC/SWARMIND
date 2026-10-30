# Spec — TDD adversarial con mutantes (gate por módulo)

> Estado: **accepted** (gate T2 activo en CI; Windows delega a WSL/Docker) — Dueño: harness (CI T2 + scripts) — Frontera: 2026-10-30.
> Base: mutmut 3.8.1 (oct-2026), Cosmic Ray/mutatest evaluados, Stryker `break`
> como referencia de umbral; T2 ya corre mutmut en CI (4 módulos).

## 1. Política (estado actual + decisiones)

| # | Decisión | Fundamento |
|---|---|---|
| MU-01 | Mutación **scoped a módulos tocados por el PR**; suite completa nocturna | mutmut maintainer en contra del gate CI directo (issue #95); costo lineal |
| MU-02 | Umbral por módulo: **core ≥ 70 %**, adapters/IO ≥ 40 %, experimentales sin gate | los últimos puntos son mutantes equivalentes; Stryker `break: 70` |
| MU-03 | Cobertura sigue como **piso separado** (≥ 80 % core); nunca sustituye mutación (un test sin asserts da 100 % coverage y 0 % mutation) | evidencia CircleCI |
| MU-04 | Config en `[tool.mutmut]` (`source_paths`, `pytest_add_cli_args_test_selection`, `mutate_only_covered_lines`) | mutmut 3.8.1 docs |
| MU-05 | **Windows: WSL obligatorio** (mutmut usa `os.fork`); en local Windows se delega a CI/Docker Linux | mutmut es POSIX-only |
| MU-06 | Novedad 3.x: `type_check_command` (mypy/pyrefly) filtra mutantes inválidos — activable, con la advertencia de que puede ocultar mutaciones relevantes (`self.x = 123 → None`) | docs mutmut |

## 2. TDD adversarial aplicado en este ciclo (evidencia)

- Los tests de `binary_tuning`/`cache_threshold`/`write_actor` escriben asserts
  de frontera (clamp min/max, ceil/floor del multiplicador, cola llena → error
  tipado, doble close idempotente) que **matan mutantes típicos**
  (`>=`→`>`, `+1`→`-1`, `or`→`and`, constantes swap).
- Verificación adversarial de tools: el cleanup RUF100 falló el gate (F5 +1)
  y la suite expuso el daño → revertido (lección en `python-314-practices.md` §2).
- `test_architecture_ratchet.py` y `test_architecture_contracts.py` son tests
  *del gate* (F7/F8): el gate mismo está bajo test (meta-verificación).

## 3. Criterios de aceptación

| Crit | Requisito |
|---|---|
| AC-MU1 | `mutmut run` sobre los módulos del PR en CI T2: parseo de `mutmut results --all true` y falla si score < umbral del módulo (core 70 %). |
| AC-MU2 | Nocturna: suite completa de mutación sobre `harness/memory_rag/{cache_geometry,compaction,reversible_compaction,shaped_cache,cache_threshold,binary_tuning,write_actor,memory_heat,memory_reconciliation}` (ya configurado en CI T2: 9 módulos + 10 archivos de test). |
| AC-MU3 | Todo mutante *survivor* en core se justifica como mutante equivalente en el PR (o se mata). |
| AC-MU4 | La suite nunca se parchea para "pintar verde": los asserts débiles (sin oráculo) se endurecen, no se eliminan. |
| AC-MU5 | En Windows local, mutación solo vía WSL/Docker (documentado en este spec). |

## 4. Referencias

- [mutmut docs](https://mutmut.readthedocs.io/en/latest/)
- [mutmut issue #95 (CI gate)](https://github.com/boxed/mutmut/issues/95)
- [CircleCI: what is mutation testing](https://circleci.com/blog/what-is-mutation-testing)
- [Estudio de competencia de herramientas (2024)](https://par.nsf.gov/servlets/purl/10573281)
- [ACM ISSTA 2024/2025 mutation](https://dl.acm.org/doi/10.1145/3701625.3701659)
