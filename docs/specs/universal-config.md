---
task_id: "universal-config"
version: "1.0.0"
created: "2026-10-08"
author: "guardian"
status: "in_progress"
---

# Spec: Config Universal — rutas, endpoints y VRAM multiplataforma

- **Estado:** propuesta + verificacion en curso (2026-10-08)
- **Principios:** `ARQ`, `SEG`, `FND`, `TST`, `ADV`, `CPD`, `IDP`, `UPG`
- **ADR:** ADR-0098 (Clean Architecture, fail-fast, inmutabilidad, tests AAA)
- **SSOT:**
  - `harness/model_router/backend_config.py` — `GpuBudget`, `BackendConfig` (`from_env`).
  - `harness/model_router/backend_launcher.py` — `detached_kwargs`, `build_launch_command`, `spawn_detached`.
- **Fitness function:** `harness/tests/test_universal_config_fitness.py`.

## 1. Propuesta (WHY + outcome medible)

**Problema.** La configuracion del backend local (rutas del binario/YAML, URL/puerto,
VRAM y techo de contexto) se resolvia con valores clavados a esta maquina y a Windows.
Migrar de GPU (8GB a 24GB), de host o de Sistema Operativo (Windows/macOS/Linux)
obligaba a editar codigo, y existia riesgo de rutas personales de la maquina
(estilo `C:\Users\<user>`, `/Users/<user>`, `/home/<user>`, `~/Mi unidad`) filtradas
en el repositorio.

**Outcome medible.** Al finalizar:

1. `uv run python -m pytest harness/tests/test_universal_config_fitness.py -q`
   pasa con 0 fallos.
2. La fitness function de portabilidad no encuentra NINGUNA ruta personal
   hardcodeada en `.py` de produccion (excluye tests, docs, `__pycache__`, `.git`).
3. `BackendConfig.from_env()` y `GpuBudget.from_env()` cumplen las invariantes
   verificadas por PBT (round-trip de entorno, precedencia, fail-fast).
4. La suite de mutacion dirigida mata los mutantes obvios de comparadores
   (`<=`/`<`), booleanos (`or`/`and`), defaults y sufijos de launcher.
5. Cero regresiones en `test_backend_config.py` y `test_backend_launcher.py`.

### Apuesta (Shape Up: appetite + boundaries)

- **Appetite:** 1 ciclo corto (spec + tests; sin tocar produccion).
- **Boundaries:** IN = specs + tests de fitness/PBT/adversarial/mutacion dirigida.
  OUT = editar codigo de produccion, integracion con GPU real, red.
- **RFC previo:** no (la refactorizacion de produccion ya esta descrita por el
  contrato existente; esta tarea solo anade verificacion).
- **Cooldown si pierde:** cognition store + deuda AGR (documentar).

## 2. Especificacion (FR / NF)

### Requisitos funcionales

- **FR-1 Portabilidad:** Windows, macOS y Linux sin editar codigo.
- **FR-2 Entorno (12-Factor):** resolucion por variables `SWARMIND_*` con default seguro.
- **FR-3 Precedencia determinista:** variable nueva gana al alias legacy.
- **FR-4 Descubrimiento sin rutas de usuario fijas:** `env -> which -> candidatos por SO`.
- **FR-5 Validacion fail-fast:** WHAT+WHY+WHERE en presupuesto, timeouts y retry.
- **FR-6 Arranque silencioso y desacoplado por plataforma.
- **FR-7 `build_launch_command`:** binario directo o launcher (`.bat`/`.cmd`/`.sh`),
  error tipado si no hay ninguno.
- **FR-8 `listen_address`** derivado coherente de `base_url` (host:puerto).

### Requisitos no funcionales

- **NF-1 Rendimiento:** resolucion de entorno O(1), sin red ni procesos reales.
- **NF-2 Seguridad:** sin `shell=True`, sin secretos, sin rutas personales.
- **NF-3 Inmutabilidad:** dataclasses `frozen=True`; sin mutar parametros.
- **NF-4 Testabilidad:** hermetico (descubrimiento y `Popen` simulados).
- **NF-5 Paths:** `pathlib` + `Path.home()`; 0 literales de nombre de usuario.

## 3. Diseno (contratos verificados)

| Contrato | Entrada | Invariante |
|---|---|---|
| `GpuBudget.from_env()` | env `SWARMIND_GPU_BUDGET_MB`/`SAFE_CTX_MAX`/... | round-trip 1:1; `safe_ctx_max>0`; `min_safe_ctx<=safe_ctx_max`; `ctx_step>0`; `0<vram_safety<=1`; `budget_mb>0`; `min_free_vram_mb>=0` |
| `BackendConfig.from_env()` | env `SWARMIND_LOCAL_BASE_URL` (+legacy `SWARMIND_LLAMA_BASE_URL`) | nueva gana a legacy; `base_url` sin slash final; `retry_attempts>=1`; `start_timeout_s>0`; `poll_interval_s>0`; `retry_backoff_s>=0` |
| `BackendConfig.listen_address` | `base_url` | `f"{hostname}:{port}"`; puerto por defecto `11434` |
| `build_launch_command` | `BackendConfig` | binario si existe; si no launcher (`.bat/.cmd` -> `cmd /c`, `.sh` -> `sh`); si no, `BackendLaunchError` |
| `detached_kwargs` | SO | Windows -> `creationflags` (NO_WINDOW+ DETACHED_PROCESS + NEW_PROCESS_GROUP); POSIX -> `start_new_session=True` |

## 4. Tareas

- [x] **T1** Spec (este documento).
- [ ] **T2** `test_no_hardcoded_machine_paths_in_production` (fitness function).
- [ ] **T3** PBT `hypothesis` de `from_env` (round-trip, precedencia, fail-fast, `listen_address`).
- [ ] **T4** Adversarial + BVA de `build_launch_command` / `detached_kwargs`.
- [ ] **T5** Mutacion dirigida (mutation-style asserts) con justificacion de `mutmut`.

## 5. Sandbox scope

- **Crea:**
  - `specs/universal-config.md`
  - `harness/tests/test_universal_config_fitness.py`
- **Modifica:** nada de produccion.
- **NO toca:** `harness/model_router/backend_config.py`,
  `harness/model_router/backend_launcher.py`, `harness/qa/security_policy.py`,
  tests existentes.

## 6. Rollback plan

1. `git checkout -- specs/universal-config.md` (si existia).
2. `Remove-Item harness/tests/test_universal_config_fitness.py`.
3. Verificar: `uv run python -m pytest harness/tests/test_backend_config.py harness/tests/test_backend_launcher.py -q`.

## 7. Exit criteria (gates)

- [ ] `uv run ruff check harness/tests/test_universal_config_fitness.py` -> 0 errores.
- [ ] `uv run python -m pytest harness/tests/test_universal_config_fitness.py harness/tests/test_backend_config.py harness/tests/test_backend_launcher.py -q` -> todos pasan.
- [ ] Fitness function: 0 rutas personales en produccion.
- [ ] PBT: invariantes verificadas con contador de ejemplos > 0.
- [ ] Mutacion: comando `mutmut` documentado + mutation-style asserts que matan mutantes obvios.

## 8. Riesgos y mitigacion

| Riesgo | Mitigacion |
|---|---|
| Falso positivo del regex de paths | Control positivo y negativo en el propio test; auto-exclusion del scanner de politica |
| `mutmut` no corre nativo en Windows | Documentar comando + WSL; sustituir por mutation-style asserts dirigidos |
| Hypothesis + fixture `monkeypatch` | Suprimir `HealthCheck.function_scoped_fixture` en `@settings` |
| Lentitud al recorrer `.venv`/`lance` | Poda de directorios en `os.walk` (topdown) |

## 9. Verificacion (comandos)

```bash
uv run ruff check harness/tests/test_universal_config_fitness.py
uv run python -m pytest harness/tests/test_universal_config_fitness.py harness/tests/test_backend_config.py harness/tests/test_backend_launcher.py -q
uvx mutmut run --paths-to-mutate harness/model_router/backend_config.py
```