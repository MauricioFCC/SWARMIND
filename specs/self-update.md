# Spec: Auto-actualización desde remoto anti-reversión (self-update)

> Estado: **accepted + implemented** (ciclo 11.21: spec → SDD → TDD
> adversarial mutante → implementación en `harness/self_update/` +
> CLI `scripts/self_update.py` + paso 7 del setup).
> Dueño: `harness/self_update/` (`core.py` + `journal.py` + `versions.py`)
> y `scripts/self_update.py`.
> Mandato: cada instalación local del harness debe leer el repo remoto,
> actualizarse cuando el remoto avanza (win/linux/mac) y dejar un **log de
> actualización que impida reversiones** (nunca degradar, nunca borrar).

## 1. Problema

SWARMIND está clonado en N máquines (Windows/Linux/macOS). El repo remoto
avanza (CI, tags, releases) pero las instalaciones locales no se enteran:
cada clon se degrada silenciosamente respecto al remoto y, cuando alguien
sincroniza a mano, un `git reset`/`checkout` mal usado puede **revertir**
commits locales o estados de la memoria. No existe trazabilidad de quién
actualizó, cuándo, ni desde/hacia qué versión.

## 2. Investigación frontera anexada (FRS)

- **Fast-forward-only como invariant de no-reversión**: `git merge
  --ff-only` solo avanza cuando `local HEAD` es ancestro del remoto ⇒
  por construcción **nunca descarta commits locales ni retrocede**; el
  trabajo divergido se detecta y aborta en vez de resolverse a la fuerza.
  Es el patrón de update channels de Chrome/VSCode-server (rollout
  forward-only con kill-switch).
- **Monotonicidad de versión (anti-downgrade)**: gates tipo "app store"
  comparan semver del remoto vs local; si `remote < local` ⇒ *blocked*.
  Aplicado a releases: nunca instalar un artefacto por debajo de la
  última versión registrada en el log (el log es la SSOT de la cota).
- **Update journaling (crash-safe)**: escribir la intención ANTES de
  mutar (WAL) y el resultado después — un update interrumpido queda como
  `failed` y no se reintenta a ciegas; el log es append-only JSONL
  (barato, greppable, a prueba de merges).
- **Supply-chain (SLSA/TUF)**: verificar que el remoto proviene del
  remoto esperado (`remote_url` fijado) y actualizar solo por canales
  oficiales (el remoto configurado, no URLs arbitrarias).
- **No-update-in-flight**: aplicar el update en punto seguro (arranque o
  CLI explícito), nunca en medio de una sesión activa; tras aplicar,
  notificar "reinicio requerido" (patrón RPA/RE-ANCHOR del harness).
- **FRS 2026 (investigación de este ciclo)**: ADR-0010 anti-rollback
  (FabianSchurig/open-connect) ⇒ **`max_seen_version` monotónico**
  persistido en el journal (no solo comparación par a par) y **downgrade
  como acción deliberada**: requiere flag `allow_downgrade=True` +
  `justification` no vacío, queda como evento `downgrade_forced` en el
  audit log (auditable + autorizado ≠ accidente). Journaling "roll
  forward": *prefix property* — si existe una actualización, existen
  todas las anteriores = exactamente el invariante de `--ff-only`
  (InterSystems/SQLite WAL). Defense-in-depth git:
  `git config branch.<b>.mergeoptions --ff-only` (git-automation 2026:
  "ff-only promotion makes divergence impossible", enforceable
  server-side) y preferir *roll-forward* sobre retroceso de puntero
  (MITRE MID-030: la referencia anti-rollback solo avanza tras
  confirmación).

## 3. Decisiones (qué hace / qué NO hace)

| Escenario | Acción | Entrada en log |
|---|---|---|
| Remoto tiene commits nuevos (ff posible) y `remote_version >= floor` | `fetch` + `merge --ff-only` | `updated` (from→to) |
| Sin commits nuevos (behind=0, o solo ahead local) | nada | `noop` |
| `remote_version < floor` donde `floor = max(local_version, max_seen_log)` | **bloquear** | `blocked_downgrade` |
| Idem, pero `allow_downgrade=True` + `justification` no vacío | ff con lo del remoto | `downgrade_forced` + justification |
| Worktree local sucio (commits/stash/modify) con cambios pendientes de pull | **abortar** sin tocar nada | `dirty_worktree` |
| Divergencia (commits locales no empujados + commits remotos) | **abortar**, nunca `reset`/`force` | `diverged` |
| Sin red / sin `git` / sin remoto / auth falla | degradar (exit 0 en startup) | `offline` / `no_git` / `no_remote` |

**NUNCA** (anti-patrones): `git reset --hard`, `checkout` a versión
anterior, `stash` drop automático, auto-update sin log, URLs de update no
fijadas, aplicar update a mitad de sesión sin reinicio. La única puerta
de reversión es `allow_downgrade=True` + `justification` no vacío, que
**nunca** reduce `max_seen_version` (el piso sigue en la cota histórica).

**Qué NO se auto-actualiza**: datos (memoria central, `.env`, worktrees no
tracked) — solo avanza el código tracked por git; los binarios/descargas
(`*.lance`, venv) quedan fuera del alcance (gitignore).

## 4. Arquitectura (a implementar)

`harness/self_update/` (funciones puras + DI de `run_git` y `now`):

- `check_remote(repo, remote="origin", branch)` → `UpdateCheck`
  (`behind`, `ahead`, `local_version`, `remote_version`, `remote_url`,
  estado enum). Usa `git ls-remote` + `git rev-list --count`.
- `apply_update(check)` → `UpdateResult`: valida remoto fijado + Worktree
  limpio + monotonic gate ⇒ `merge --ff-only` ⇒ WAL `attempt` → `result`.
- `parse_version(repo)` — fuente única: `pyproject.toml` `version` +
  fallback `git describe --tags` (semver estricto, comparable con tuple).
- `append_log(entry)` / `audit_log(path)` — JSONL append-only; `audit_log`
  verifica el invariante de monotonicidad (`updated.to >= updated.from`
  y `to >= máx(aplicadas previas)`); cualquier violación ⇒ `reversion`
  detectada (exit != 0).
- Log primario: `<repo>/.swarmind/update_log.jsonl` (travanea el ff-pull,
  sobrevive re-clones locales); espejo en
  `<MEMORY_ROOT>/logs/self_update.jsonl` (auditoría entre instalaciones).

CLI `scripts/self_update.py`: `--check` (solo informa), `--apply`
(explicito), `--audit` (revisa el log); en startup de `setup_swarmind.py`
paso 8 (post-verificación) corre `--check --apply` con degradación
suave (nunca bloquea el setup si falla).

Cross-platform: `pathlib` + `subprocess` sin `shell=True`; resolución de
`git` en PATH (`git.exe` en Windows); remoto local `file://` para tests
(repos bare en tmp ⇒ escenarios ff/behind/diverged reales sin red).

## 5. Contratos (TDD — ciclo 11.21)

`harness/tests/test_self_update.py` (remotos bare locales vía path —
sin red, cross-platform con git real):

1. `check_remote` detecta `BEHIND behind=2` contra un bare repo local.
2. Sin commits nuevos ⇒ `UP_TO_DATE behind=0`.
3. `apply_update` hace ff y registra `updated` con from/to exactos
   (versión + commit + máquina + OS).
4. Remoto revierte la versión (`remote < floor = max(local, max_seen)`)
   ⇒ `blocked_downgrade` + **0 cambios en worktree**.
5. `allow_downgrade=True` + justification no vacío ⇒ `downgrade_forced`
   con justification en el log; `max_seen` NO baja.
6. `allow_downgrade` sin justification ⇒ se rechaza (queda como blocked).
7. Archivos sucios (detrás) ⇒ `dirty_worktree` + 0 cambios (nunca stash).
8. Divergencia (local ahead + remote behind) ⇒ `diverged` + 0 cambios
   (nunca reset).
9. Sin red (runner inyectado falla el fetch) ⇒ `offline`, exit 0.
10. `git` ausente (runner 127) ⇒ `no_git`; remoto inexistente ⇒ `no_remote`.
11. `append_log` append-only: 3 entradas ⇒ 3 líneas JSON válidas.
12. `audit_log` detecta reversión (`to < from` o `to < max(previas)` y
    `downgrade_forced` sin justification) — mutante debe morir; log limpio
    ⇒ 0 violaciones.
13. `max_seen_version` devuelve la cota histórica tras updates + vacío ⇒
    `(0, 0, 0)`.
14. Idempotencia: segunda `apply_update` tras ff ⇒ `noop` (1 sola
    `updated` en el historial).

Kill-check: flips de comparação en el monotonic gate + direction de ff +
orden WAL (attempt antes que result). Suite + ruff + vulture.

## 6. Verificación

RED→GREEN→kill-check→suite completa; prueba manual con remoto `file://`
en las 3 plataformas (CI matrix); `--audit` sobre el log real de esta
máquina tras la primera actualización.

## 7. Criterios de aceptación

- [ ] Una instalación local avanza al remoto sin intervención manual y sin
      poder retroceder (ff-only + monotonic gate + audit).
- [ ] Toda actualización queda en JSONL con from/to/os/machine/resultado.
- [ ] `audit_log` del historial ⇒ 0 reversiones (invariante verificado).
- [ ] Sin red/git/auth: degradación limpia, 0 excepciones no manejadas.
- [ ] Windows/Linux/macOS: misma ruta de código (pathlib, sin shells).
