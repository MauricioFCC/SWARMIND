# SPEC — Baseline Architecture Repo (esqueleto universal estado de arte)

> Estado: **nueva** (2026-11-05, ciclo `frontier-engineering` 11.75).
> Research: `docs/research/frontier-2026-11-05-baseline-architecture.md`.
> Entregable: carpeta `Baseline-Architecture-Repo/` (fuera de este repo, se
> copia y renombra como esqueleto de futuros proyectos; **sin `.git` propio**
> para no arrastrar historial al copiar).

## Outcome medible

Copia `Baseline-Architecture-Repo/` → renombra → `git init` → CI verde en la
primera corrida, con: contrato de agente corto, docs base, ADRs/specs con
plantillas, gates ejecutables (ruff/complexity/pytest/coverage) y un **auditor
de deriva** que detecta en Θ(P·F) cuánto un proyecto copiado divergió del
baseline (exit 0/1/2).

## FR (requerimientos funcionales)

1. **FR-BL1 — Estructura**: `AGENTS.md` (≤150 líneas, 6 secciones:
   comandos/testing/estilo/estructura/git/límites), `README.md` con checklist
   de copia, `docs/{README,conventions,architecture,testing,roadmap}.md`,
   `docs/adr/{README,0001,TEMPLATE}`, `docs/specs/TEMPLATE.md`,
   `CHANGELOG.md`, `CONTRIBUTING.md`, `.editorconfig`, `.gitignore`,
   `.gitattributes`, `.pre-commit-config.yaml`, `pyproject.toml`,
   `.github/workflows/ci.yml`.
2. **FR-BL2 — Núcleo algorítmico** `scripts/baseline_check.py` (stdlib):
   `build_manifest(root, excludes) -> {ruta: sha256}` (Θ(F·b)),
   `diff(root, manifest) -> DriftReport(faltantes, cambiados, locales,
   sin_cambios)` (Θ(F), lookup O(1) + fast-path size/mtime),
   `audit_fleet(manifest, [proyectos]) -> {proyecto: DriftReport}`
   (Θ(F·b) + Θ(P·F)); CLI `check|update|audit --json`; exits 0/1/2.
3. **FR-BL3 — Manifiesto**: `baseline_manifest.json` versionado
   (`{version, files:{rel: sha256, size}}`), **auto-excluido** (sin
   auto-referencia), regenerable con `update`; exclusiones por patrón
   (`.git`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `*.pyc`,
   `baseline_manifest.json`).
4. **FR-BL4 — CI día 1**: workflow que ejecuta `ruff check`,
   `ruff --select C901` (complejidad ≤10) y `pytest` con
   `fail_under=80`; `.pre-commit-config` espejo local.
5. **FR-BL5 — Reutilización (IDP)**: primitivas `digest/manifest/excludes`
   vendoreadas de `scripts/propagation.py` (11.74) con atribución; NO se
   reimplementan; el delta nuevo es diff+auditoría+CLI.

## NF (no funcionales)

- Stdlib puro en `scripts/` y `tests/` salvo `pytest`/`hypothesis` como dev
  (hypothesis ya presente en el ecosistema); docstrings ES; type hints; 0
  `except` silenciosos; sin rutas personales ni secretos en ningún fichero.
- Complejidad de función ≤30 líneas (estilo del ecosistema).
- Portabilidad: Windows-first, 0 `.bat/.ps1/.cmd/.sh` (Python + YAML CI).

## Exit criteria (gate)

- [ ] `pytest <baseline>/tests -q` ≥ 18 passed, 0 failed (unit+PBT+equivalencia+mutantes).
- [ ] Contadores N/2N/4N: lineal exacto (`ops(4N)/ops(N) == 4`) y naïve
      referencia cuadrática (`== 16`) + equivalencia naïve↔nuevo en N chico.
- [ ] Mutantes: ≥5 mutantes **killed** (test de mutantes falla si el módulo
      se relaja).
- [ ] `ruff check <baseline>` exit 0 (incl. C901) y `pytest --cov` ≥ 80 %.
- [ ] SWARMIND: `pytest harness/tests -q` 0 failed (regresión), `ruff check`
      exit 0, `vulture` 0, `check_architecture`/`check_complexity`/
      `check_ruff_ratchet`/`check_ruff_preview`/`audit_pep649`/
      `validate_skills --strict` exit 0.
- [ ] Docs: research (fase 2), spec (ésta), CHANGELOG 11.75, roadmap, MEJORAS,
      ADR-0105; commit convencional en español; `publish.py` ejecutado.

## Rollback

Borrar `Baseline-Architecture-Repo/`; revertir el commit de docs en este repo;
ningún archivo del harness cambia de comportamiento (el baseline vive fuera
del repo).
