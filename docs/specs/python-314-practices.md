# Spec — Prácticas Python 3.14 + tooling de verificación (2026)

> Estado: accepted — Dueño: harness (todo el repo) — Frontera: 2026-10-30.
> Fuentes verificadas: docs.python.org (whatsnew 3.13/3.14/3.15), PEPs
> 703/744/749/758/836, pytest-asyncio 1.x, mutmut 3.8.1, ruff 0.17.1,
> mypy 2.0, hypothesis latest. Detalle de hallazgos en la investigación del ciclo.

## 1. Reglas vigentes (aplicadas en este ciclo)

| # | Regla | Evidencia aplicada |
|---|---|---|
| PY-01 | `asyncio.iscoroutinefunction` (removal 3.16) → `inspect.iscoroutinefunction` | `harness/parallel/io_fusion.py`, `harness/parallel/pipeline_macu.py` |
| PY-02 | Declarar `asyncio_default_fixture_loop_scope` / `asyncio_default_test_loop_scope` (default cambiará a `function`) | `pyproject.toml` |
| PY-03 | Hypothesis con perfil por entorno: `ci` (`derandomize`, `database=None`, `deadline=None`) / `dev` | `harness/tests/conftest.py` (`HYPOTHESIS_PROFILE`) |
| PY-04 | Free-threaded: build separado `python3.14t`, no default; no planificar rendimiento sobre JIT (PEP 744 experimental; PEP 836 retirado 2026-10-19) | CI usa build GIL estándar |
| PY-05 | PEP 649/749: anotaciones diferidas — auditar `__annotations__`/`get_type_hints` antes de subir `requires-python` | **hecho**: `scripts/audit_pep649.py` + baseline con 3 usos justificados (`inspect.signature` en scripts); el kernel no introspecciona; 8 tests de contrato (`test_pep649_annotations.py`) |
| PY-06 | mypy 2.x: `-n auto` en CI (cap 8 workers); strict incremental por `[[tool.mypy.overrides]]`, empezando por `harness/kernel/` y `harness/domain/` | **hecho**: `pyproject.toml` + job `type-check` bloqueante (7 archivos strict-clean) |
| PY-07 | Ruff `preview=true` solo en `[tool.ruff.lint]`; adoptar PERF/FURB/RUF con ratchet, nunca big-bang | **hecho (allowlist)**: `scripts/check_ruff_preview.py` fija 10 códigos en cero; `check_ruff_ratchet.py` vigila el resto. `preview=true` global **no** se activa (Ruff 0.16.6 habilita 138 reglas preview ajenas, medido) |
| PY-08 | `per-file-ignores` heredado: usar `extend-per-file-ignores` (el otro *reemplaza*) | convención de config |

## 2. Lección adversarial verificada (RUF100, 2026-10-30)

Ejecutar `ruff check --select RUF100 --fix` fue **destructivo**: RUF100 evalúa
"unused" contra el rule-set activo de esa corrida (`--select` *reemplaza* la
config), así que **todos** los noqa de otras reglas aparecieron como unused y
se eliminaron 437, exponiendo 452 violaciones reales (BLE001/SIM117/F401/...).
Revertido con `git checkout` y re-aplicados los fixes válidos por separado.

**Regla nueva (PY-09)**: nunca aplicar auto-fix de reglas *meta* (RUF100,
`\*noqa`) con `--select` aislado; hacerlo solo con la config completa del repo
y tras ejecutar la suite. El gate (`--gate --ratchet`) más tests es el
verificador adversarial del propio tooling.

## 3. Deuda aceptada con baseline (P2)

Auditoría con `--preview --select PERF,FURB,RUF` (2026-10-30):

| Regla | Conteo | Acción |
|---|---|---|
| RUF069 (float equality `==`) | 475 | revisar por módulo (matemática tolerante) |
| RUF100 (unused-noqa) | 438 | **no se auto-fixea**: `--select RUF100` evalúa contra el rule-set activo y borra noqa válidos (lección §2). Queda bajo el ratchet (solo falla si sube). |
| RUF052 (used `_` var) | 97 | renombrar |
| PERF401 (comprehension) | 65 | refactor progresivo |
| RUF067/FURB113/FURB118/... | ~150 | refactor progresivo |

Política: adoptar `preview=true` + `extend-select` cuando el conteo baje
(ratchet tipo F7), no antes.

## 4. Criterios de aceptación

| Crit | Requisito |
|---|---|
| AC-PY1 | 0 warnings `PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET)` en la suite. |
| AC-PY2 | `HYPOTHESIS_PROFILE=ci pytest` corre sin crear `.hypothesis/` ni flakes por deadline. |
| AC-PY3 | 0 usos de `asyncio.iscoroutinefunction` en `harness/**` (removal 3.16). |
| AC-PY4 | 0 falsos "unused import schedule/torch": toda dependencia declarada tiene import activo o se retira. |
| AC-PY5 | `pip install .` en contenedor no descarga torch/nvidia (verificado: 15 s). |
