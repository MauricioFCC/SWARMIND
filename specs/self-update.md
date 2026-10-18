# Spec: Auto-actualización desde remoto anti-reversión (self-update)

> Estado: **proposed** (spec-only, ciclo 11.21 = implementación TDD).
> Dueño: `scripts/self_update.py` + `harness/self_update/` (a crear).
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

## 3. Decisiones (qué hace / qué NO hace)

| Escenario | Acción | Entrada en log |
|---|---|---|
| Remoto tiene commits nuevos (ff posible) y `remote_version > local` | `fetch` + `merge --ff-only` | `updated` (from→to) |
| Igual versión/commit | nada | `noop` (solo `--check` lo imprime) |
| `remote_version < local_version` (remoto atrasado o clon adelantado) | **bloquear** | `blocked_downgrade` |
| Worktree local sucio (commits/stash/modify) | **abortar** sin tocar nada | `dirty_worktree` |
| Divergencia (commits locales no empujados) | **abortar**, nunca `reset`/`force` | `diverged` |
| Sin red / sin `git` / auth falla | degradar (exit 0 en startup) | `offline` / `no_git` / `auth_failed` |

**NUNCA** (anti-patrones): `git reset --hard`, `checkout` a versión
anterior, `stash` drop automático, auto-update sin log, URLs de update no
fijadas, aplicar update a mitad de sesión sin reinicio.

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

`harness/tests/test_self_update.py`:

1. `check_remote` detecta `behind=3` contra un bare repo local.
2. `apply_update` hace ff y registra `updated` con from/to exactos.
3. Remoto más viejo ⇒ `blocked_downgrade` + **0 cambios en worktree**.
4. Archivos sucios ⇒ `dirty_worktree` + 0 cambios (nunca stash).
5. Commit local no empujado ⇒ `diverged` + 0 cambios (nunca reset).
6. Sin red (run_git inyectado que falla) ⇒ `offline`, exit 0 en startup.
7. `append_log` es append-only: 100 entradas ⇒ 100 líneas JSON válidas.
8. `audit_log` marca reversion si `to < from` (mutante debe morir).
9. Log espejo en MEMORY_ROOT se escribe igual.
10. Idempotencia: segunda `apply_update` tras ff ⇒ `noop`.

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
