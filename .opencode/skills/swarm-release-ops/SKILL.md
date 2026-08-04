---
name: swarm-release-ops
domain: swarm-release-ops
version: 1.0.0
description: "Release engineering y CI/CD de SWARMIND: GitHub Actions, uv, safety, bandit, auto-merge, branch protection. Usar con release, CI, workflow, pipeline, deploy, checks rojos | UPG·NAM·FRS (reglas en base_principles.md)"
---

# Swarm Release Ops | Release Engineering y CI/CD de SWARMIND

Skill contextual muy especializado en la operacion de releases del repo
`MauricioFCC/SWARMIND`. Complementa a `devops-infra` con el conocimiento
empirico verificado del CI de este proyecto.

## Doctrina (Hedge Fund)

Cada release es una asignacion de capital: riesgo/reward, mandato y stop-loss.
Un CI rojo es una perdida de capital operativo — se atiende con prioridad,
evidencia y sin parches cosmeticos (mandato: fix real + test que lo cubra).

## Stack y convenciones verificadas (agosto 2026)

- **Python**: `requires-python = ">=3.12"` (pyproject.toml). CI usa `uv`.
- **uv** es el gestor: `uv sync` + `uv run <cmd>`. El venv NO se activa solo.
  Todo job de CI debe usar `uv run` (fix historico commit `8c9429d`).
- **pyproject.toml**: `[dependency-groups].test` y `[tool.ruff] ignore EXE001`
  son REQUERIDOS — se pierden silenciosamente en refactors del lockfile
  (fixes historicos `ca2dad8`, `38d41a1`).
- **Runner**: `ubuntu-latest` (24.04). Nunca asumir Windows en CI.

## Jobs del workflow CI (`.github/workflows/ci.yml`)

| Job | Comando esencial | Nota |
|-----|-----------------|------|
| Lint | `uv run ruff check .` + `uv run ruff format --check .` | EXE001 ignorado |
| Compile | `uv run python -m compileall` | — |
| Test | `uv run pytest harness/tests` | coverage real ~80.8% |
| Agents | `uv run pytest harness/tests/test_agents.py` (u orquestador) | — |
| Security | `uv export` + `uv run safety check -r` + `uv run bandit -r harness/ -x harness/tests -ll -q` | ver abajo |
| Docs | build de docs | — |

## Seguridad: auditar el LOCKFILE, no el sistema

`pip-audit` audita el Python del sistema (setuptools 79.0.1 vulnerable,
CVE-2026-3447). El patron correcto (fix historico `a032c36`):

```bash
uv export --format requirements-txt --no-hashes > /tmp/requirements.txt
uv run safety check -r /tmp/requirements.txt --output text
```

- `setuptools>=83` en pyproject para evitar el CVE en la resolucion.
- Limitacion conocida: safety audita solo lo exportado (sin `--all-groups`
  no audita el grupo test); git deps no se auditaban — hoy no aplica
  (lockfile 100% pypi). CodeQL + dependabot como red de respaldo.

## Branch protection y auto-merge (bloqueos historicos)

- Branch protection de `main` exige checks **exactos y case-sensitive**:
  `Lint`, `Test`, `Security` (display names de los jobs con `name:`).
  Si los names no coinciden, el PR queda `BLOCKED` ("Expected — Waiting").
- `required_conversation_resolution: true` — los review threads sin resolver
  bloquean el merge.
- Auto-merge on green (`.github/workflows/auto-merge.yml`): requiere
  `permissions: contents: write` + `pull-requests: write` (fallo historico
  "Resource not accessible by integration"); usar `peter-evans` @v3 o
  `gh pr merge --squash --auto`.
- `mergeStateStatus: BLOCKED` + todo verde = configuracion, no codigo.

## Tests: portabilidad Windows/Linux

- Nunca backslashes literales en asserts de paths: usar `os.sep` o `Path`
  (fix historico `113d3d6`).
- Evitar asserts de texto exacto del broadcast/async (flaky): verificar
  contrato ASCII estable (ej. `SubtaskID`) o vacio/no-generico.
- Preferir `tmp_path` de pytest sobre `/tmp` hardcodeado.

## Checklist de release

1. `gh pr view <n> --json state,statusCheckRollup,mergeStateStatus` — todo verde
   y `MERGEABLE`, no `BLOCKED`.
2. Resolver threads pendientes (GraphQL `reviewThreads`, `isResolved: false`).
3. `gh pr merge <n> --squash` (o `--auto` si aplica).
4. Post-merge: verificar que el run de `release.yml` no quede en
   "failure 0s" (workflow fantasma — revisar pestaña Actions).
5. Tag semver si el changelog lo amerita; verificar docs builds.

## Anti-patrones (prohibidos)

- `pip install` directo en CI (usar uv).
- `pip-audit` como gate de seguridad (audita sistema, no lockfile).
- Parches cosmeticos a tests para "pintar verde": el test debe poder fallar.
- Asumir `python-version: 3.11` en setup-python cuando el proyecto exige
  `>=3.12` (uv descarga/usa el requerido, pero el pin miente).
