# Spec — TDD adversarial con mutantes (gate por módulo)

> Estado: **implemented** (mutación scoped por `git diff` + umbrales por paquete) — Dueño: harness (CI T2 + scripts) — Frontera: 2026-10-30.
> Base: mutmut 3.8.1 (oct-2026), Cosmic Ray/mutatest evaluados, Stryker `break`
> como referencia de umbral. Implementación: `scripts/mutation_scope.py`.

## 1. Política (estado actual + decisiones)

| # | Decisión | Fundamento |
|---|---|---|
| MU-01 | Mutación **scoped a los archivos tocados por el PR** (`git diff base...HEAD`); una corrida por paquete afectado | mutmut maintainer en contra del gate CI directo (issue #95); costo lineal |
| MU-02 | Umbral por **paquete**, no global: kernel **90 %** (alcanzado: 90.8 % el 2026-11-07), domain **75 %**, memory_rag **70 %**, resto **40 %** | los últimos puntos son mutantes equivalentes; Stryker `break: 70`; core más exigente que adapters. La primera medición real de kernel fue 62.6 %, así que el umbral se calibró a un baseline transitorio (0.60 + ratchet 0.62) y volvió a la meta cuando la ronda de asserts de `test_kernel.py` llevó el score a 90.8 % |
| MU-03 | Cobertura sigue como **piso separado** (≥ 80 % core); nunca sustituye mutación (un test sin asserts da 100 % coverage y 0 % mutation) | evidencia CircleCI |
| MU-04 | Config generada en `[mutmut]` (`source_paths`, `only_mutate`, `pytest_add_cli_args_test_selection`) desde el diff | mutmut 3.8.1: esas claves son las de 3.x (`--paths-to-mutate` es 2.x) |
| MU-05 | **Windows: WSL/CI obligatorio** (`--run` devuelve 2 con instrucciones); `--dry-run`/`--write-config` sí funcionan | mutmut usa `os.fork` (POSIX-only) |
| MU-06 | `type_check_command` (mypy/pyrefly) disponible para filtrar mutantes inválidos, con la advertencia de que puede ocultar mutaciones relevantes (`self.x = 123 → None`) | docs mutmut |
| MU-07 | Sin cambios mutables en el diff → **skip** (no se muta de más) | el costo se paga solo por lo que cambió |
| MU-08 | `@runtime_checkable Protocol` y `__init__.py` → `do_not_mutate`; un paquete sin lógica se **omite** | mutmut inyecta métodos `__mutmut_*` en la fuente; en un Protocol esos métodos pasan a ser atributos del contrato y `isinstance(store, VectorStorePort)` da `False` aunque el store implemente todo (15 atributos, 5 inyectados) → `TypeError` en stats. Los `__init__.py` solo re-exportan y sus mutantes no tienen tests |
| MU-09 | Selección de tests = homónimo + módulo + **paquete** + **stem del nombre** | `from harness.kernel import X` no contiene el literal `harness.kernel.mailbox`; sin esto se elegían tests ajenos y el score salía 0.0 % |
| MU-10 | Baseline de ratchet por paquete (`scripts/mutation_baseline.json`), solo sube con `--update-baseline` | el umbral de config es el suelo: el gate falla si `score < max(config, baseline)` |
| MU-11 | Los tests seleccionados deben ser **herméticos ante repeticiones en el mismo proceso** (`lru_cache`, `sys.modules`, símbolos PEP 562) | mutmut ejecuta `stats` y luego `clean tests` con `pytest.main()` en un mismo proceso: sin hermeticidad el segundo arranque falla y el score sale 0.0 % |

## 2. Implementación (`scripts/mutation_scope.py`)

1. `changed_files(base)` → `git diff --name-only --diff-filter=ACMR base...HEAD`
   filtrado a `harness/**/*.py` fuera de tests.
2. `package_for(path)` → prefijo más específico; `threshold_for(pkg)` → umbral.
3. `find_tests(source)` → `test_<stem>.py`, tests que importan el módulo
   (`harness.pkg.mod`), tests que importan el **paquete**
   (`from harness.pkg import ...`) o `test_<pkg>_<stem>.py`.
4. `render_config(...)` → `setup.cfg` de mutmut: `source_paths`,
   `also_copy` (`scripts/`, `.opencode/`), `only_mutate`, `do_not_mutate`
   (protocolos y `__init__.py`) y la selección de tests.
5. `--run` (POSIX): omite paquetes sin lógica, mutmut +
   `export-cicd-stats` + `score_from_stats` + `evaluate` contra
   `max(umbral, baseline)`; `--update-baseline` sube el baseline (nunca baja).
6. `--check-stats FILE --package PKG` para depurar un stats ya generado.

CI: el job `mutation` usa
`python scripts/mutation_scope.py --base <base_sha> --run --max-children 2`.

## 3. TDD adversarial aplicado (evidencia)

- Los tests de `binary_tuning`/`cache_threshold`/`write_actor` escriben asserts
  de frontera (clamp min/max, ceil/floor del multiplicador, cola llena → error
  tipado, doble close idempotente) que **matan mutantes típicos**
  (`>=`→`>`, `+1`→`-1`, `or`→`and`, constantes swap).
- `test_mutation_scope.py` (34 tests) cubre el propio gate: mapeo
  paquete→umbral, filtro de mutables, selección por import/paquete/stem,
  fórmula del score, umbral por paquete, baseline (carga/subida), omisión de
  paquetes sin lógica, `also_copy` y `--check-stats`.
- **Evidencia de medición real** (WSL Ubuntu 26.04, mutmut 3.8.1,
  2026-11-07): primera corrida `--all-core --run` → 286 mutantes,
  **176 muertos / 105 sobrevivientes / 62.6 %** en `harness/kernel` (antes:
  crash de recolección o 0.0 %). Tras la ronda de asserts guiada por
  `mutmut results` + `mutmut show`: **257 muertos / 26 sobrevivientes /
  90.8 %** → el umbral vuelve a 0.90 y `--update-baseline` fija el ratchet.
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
