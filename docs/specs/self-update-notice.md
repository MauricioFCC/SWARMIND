# Spec — Aviso de update en runtime (instalacion nueva vs repo que avanza)

> Estado: **implemented** (ciclo 11.66) — Same revision: 2026-10-30.
> Dueño: `harness/self_update/notice.py` + `run_commands._handle_update` +
> `run_support.print_update_notice_if_due` (arranque de `python -m harness`).
> Responde: una instalacion nueva NO avisaba al usuario cuando el repo remoto
> avanzaba; hoy solo `python scripts/self_update.py --check` lo dice, y nadie
> lo ejecuta por defecto.
> Evidencia: 15 tests de notice + 7 de `!update` + 4 del hook de arranque.

## 1. Comportamiento objetivo

| Situacion | Que ve el usuario | Accion sugerida |
|---|---|---|
| Arranque y origin tiene commits nuevos (BEHIND) | Un aviso UNA vez por cooldown: "origin: N commits nuevos, version remota X.Y.Z. Ejecuta `!update check`" | `!update check` → decidir |
| Arranque y sin cambios / anclado | Nada (elimina ruido) | — |
| Arranque sin red / sin git / sin remote | Nada (degradado silencioso) | — |
| `!update` (室温 en el CLI viviente) | `estado=... behind=N local=... remote=...` | decidir apply |
| `!update apply` | `accion=... changed=... detail=...` (mismos guards anti-reversion) | — |
| `!update audit` | monotonicidad del journal | — |
| Segundo arranque dentro del cooldown | Nada (rate-limit; 0 fetch) | — |

## 2. Decisiones

| # | Decision | Fundamento |
|---|---|---|
| SU-01 | El aviso empieza al iniciar (`python -m harness`) y en `!update` | punto seguro pedido por la spec (no actualizar en medio de una sesión activa) |
| SU-02 | Rate-limit por cooldown (`24h` default) en un state JSON local (`.swarmind/update_notice.json`) | evita fetch en cada arranque (latencia + red); NO cachea fallos de red (reintento pronto) |
| SU-03 | Env `SWARMIND_UPDATE_CHECK=0` desactiva el aviso | escape hatch para offline/servidores |
| SU-04 | El aviso NO muta el repo; resume check_remote y sugiere el comando | la única puerta de mutacion sigue siendo `!update apply` con los guards del spec |
| SU-05 | El aviso nunca lanza: excepciones → `None` + log debug | la.feature no debe bloquear el arranque (patron de `_self_update` en setup) |
| SU-06 | `!update` registra el journal con los guards existentes (`allow_downgrade` + justification) | SSOT: no duplica el policy de core.py |

## 3. Criterios de aceptación

| Crit | Requisito | Test |
|---|---|---|
| AC-SU1 | BEHIND produce aviso con N y comando; el state se marca al fetch exitoso. | `test_self_update_notice.py` |
| AC-SU2 | Cooldown: segunda llamada dentro de la ventana no hace fetch (0 llamadas git). | test cooldown |
| AC-SU3 | OFFLINE/NO_GIT/NO_REMOTE → None y **sin** escribir state (reintento pronto). | test offline |
| AC-SU4 | Excepciones → None (nuna rompe el arranque). | test excepciones |
| AC-SU5 | `!update check/apply/audit` rutea por `_COMMAND_TABLE` y usa los guards del core. | `test_run_commands_update.py` |
| AC-SU6 | Arranque de `harness` imprime el aviso una vez por cooldown; env `=0` lo apaga. | test del helper |
| AC-SU7 | El aviso no requieres tokens (0 LLM) ni muta el repo. | por diseño (check solo lectura) |

## 4. Referencias

- `docs/specs/self-update.md` (guardes base, ff-only, max_seen_version).
- `harness/self_update/core.py` (check_remote, apply_update, audit_log).
- `scripts/self_update.py` (CLI standalone que sigue funcionando).
