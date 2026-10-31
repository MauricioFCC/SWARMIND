# Spec — TDD adversarial con mutantes (gate por módulo)

> Estado: **implemented** (mutación scoped por `git diff` + umbrales por paquete) — Dueño: harness (CI T2 + scripts) — Frontera: 2026-10-30.
> Base: mutmut 3.8.1 (oct-2026), Cosmic Ray/mutatest evaluados, Stryker `break`
> como referencia de umbral. Implementación: `scripts/mutation_scope.py`.

## 1. Política (estado actual + decisiones)

| # | Decisión | Fundamento |
|---|---|---|
| MU-01 | Mutación **scoped a los archivos tocados por el PR** (`git diff base...HEAD`); una corrida por paquete afectado | mutmut maintainer en contra del gate CI directo (issue #95); costo lineal |
| MU-02 | Umbral por **paquete**, no global: kernel **90 %**, domain **75 %**, memory_rag **70 %**, resto **40 %** | los últimos puntos son mutantes equivalentes; Stryker `break: 70`; core más exigente que adapters |
| MU-03 | Cobertura sigue como **piso separado** (≥ 80 % core); nunca sustituye mutación (un test sin asserts da 100 % coverage y 0 % mutation) | evidencia CircleCI |
| MU-04 | Config generada en `[mutmut]` (`source_paths`, `only_mutate`, `pytest_add_cli_args_test_selection`) desde el diff | mutmut 3.8.1: esas claves son las de 3.x (`--paths-to-mutate` es 2.x) |
| MU-05 | **Windows: WSL/CI obligatorio** (`--run` devuelve 2 con instrucciones); `--dry-run`/`--write-config` sí funcionan | mutmut usa `os.fork` (POSIX-only) |
| MU-06 | `type_check_command` (mypy/pyrefly) disponible para filtrar mutantes inválidos, con la advertencia de que puede ocultar mutaciones relevantes (`self.x = 123 → None`) | docs mutmut |
| MU-07 | Sin cambios mutables en el diff → **skip** (no se muta de más) | el costo se paga solo por lo que cambió |

## 2. Implementación (`scripts/mutation_scope.py`)

1. `changed_files(base)` → `git diff --name-only --diff-filter=ACMR base...HEAD`
   filtrado a `harness/**/*.py` fuera de tests.
2. `package_for(path)` → prefijo más específico; `threshold_for(pkg)` → umbral.
3. `find_tests(source)` → `test_<stem>.py` o tests que importan el módulo
   (`harness.pkg.mod` / `from harness.pkg import mod`).
4. `render_config(...)` → `setup.cfg` de mutmut para ese paquete.
5. `--run` (POSIX): mutmut + `export-cicd-stats` + `score_from_stats` +
   `evaluate` contra el umbral del paquete.
6. `--check-stats FILE --package PKG` para depurar un stats ya generado.

CI: el job `mutation` usa
`python scripts/mutation_scope.py --base <base_sha> --run --max-children 2`.

## 3. TDD adversarial aplicado (evidencia)

- Los tests de `binary_tuning`/`cache_threshold`/`write_actor` escriben asserts
  de frontera (clamp min/max, ceil/floor del multiplicador, cola llena → error
  tipado, doble close idempotente) que **matan mutantes típicos**
  (`>=`→`>`, `+1`→`-1`, `or`→`and`, constantes swap).
- `test_mutation_scope.py` (18 tests) cubre el propio gate: mapeo paquete→umbral,
  filtro de mutables, tests por import, fórmula del score, umbral por paquete y
  `--check-stats`.
- Verificación adversarial de tools: el cleanup RUF100 falló el gate (F5 +1)
  y la suite expuso el daño → revertido (lección en `python-314-practices.md` §2).

## 4. Criterios de aceptación

| Crit | Requisito | Estado |
|---|---|---|
| AC-MU1 | CI T2 muta solo los archivos del PR y falla si el score del paquete < umbral. | **Cumplido**: `mutation_scope.py --run` (job `mutation`) |
| AC-MU2 | Umbrales por paquete (kernel 90, domain 75, memory_rag 70, resto 40). | **Cumplido**: `MUTATION_THRESHOLDS` + tests |
| AC-MU3 | Todo mutante *survivor* en core se justifica como equivalente o se mata. | Política de revisión (PR) |
| AC-MU4 | La suite nunca se parchea para "pintar verde": asserts débiles se endurecen. | Política (agent-rigor) |
| AC-MU5 | En Windows local, `--run` no se ejecuta; se documenta WSL/CI. | **Cumplido**: guard `os.name != "posix"` → exit 2 |
| AC-MU6 | Sin archivos mutables en el diff, el job no muta nada (skip limpio). | **Cumplido**: `scope` vacío → exit 0 |
| AC-MU7 | El mapeo fuente→tests nunca deja un mutante sin runner por configuración. | **Cumplido**: `find_tests` por nombre+import (test dedicado) |

## 5. Referencias

- [mutmut docs](https://mutmut.readthedocs.io/en/latest/)
- [mutmut README (config 3.x)](https://raw.githubusercontent.com/boxed/mutmut/master/README.rst)
- [mutmut issue #95 (CI gate)](https://github.com/boxed/mutmut/issues/95)
- [CircleCI: what is mutation testing](https://circleci.com/blog/what-is-mutation-testing)
- [Estudio de competencia de herramientas (2024)](https://par.nsf.gov/servlets/purl/10573281)
- [ACM ISSTA 2024/2025 mutation](https://dl.acm.org/doi/10.1145/3701625.3701659)
