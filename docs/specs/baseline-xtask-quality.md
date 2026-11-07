# SPEC — Trinquetes de calidad xtask → estructura baseline (Rust-first, universal)

> Estado: **nueva + amendida** (2026-11-06, ciclo `frontier-engineering` 11.76).
> **Diff (2026-11-06, decisión del usuario)**: *"cambié el lenguaje de python
> por rust, mejor; escribe todo el código y ejemplos en rust"*. Rationale:
> `scripts/quality.py` y `scripts/baseline_check.py` (aprobados en RED→GREEN
> con19+18 tests) se **portan íntegros** a la crate `xtask` (subcomandos
> `check|ratchet|trace|drift`), se eliminan los artefactos Python del baseline
> (pyproject/tests .py) y todos los ejemplos del esqueleto pasan a Rust.
> `Δquality > 0` (un solo lenguaje de automatización + mutantes reales con
> harness que re-compila copias mutadas + sin toolchain doble) ∧ `Δcost < 0`
> (misma semántica ya probada, portada, no rediseñada).
> Research: `docs/research/frontier-2026-11-06-xtask-ratchets.md`.
> IDP: port de `CQE crates/cqe-xtask` (gate/arch/trace/mutation) y
> `RuscaDB crates/xtask/guards.rs` (architecture/unsafe/specs/mutation_score);
> no se reimplementan sus plataformas, se portan sus **mecanismos**.

## Outcome medible

`Baseline-Architecture-Repo/` ejecuta sus trinquetes con un comando por
lenguaje — `cargo xtask gate` (Rust) y `python scripts/quality.py check`
(universal) — con tabla PASS/FAIL/SKIP, exits 0/1/2 y un baseline
(`quality_baseline.json`) que **solo puede bajar**; ejemplos de gates en
Rust/Python/Go/web documentados con fuentes leídas.

## FR

1. **FR-XT1 — xtask Rust ÚNICO lenguaje del código** (patrón matklad):
   `Cargo.toml` workspace + `.cargo/config.toml` (alias `xtask` +
   `[build] warnings = "deny"`) + crate `xtask` **std-only** con
   `gate` (fmt+clippy `-D warnings`+arch+ratchet con `--fast`),
   `arch` (architecture.toml vs grafo workspace: desconocida/obsoleto/
   **arista prohibida** por set/**ciclos** con contador Θ(V+E)),
   `ratchet` (baseline decrease-only; parser de línea de su esquema propio),
   `check` (port universal de `quality.py`: markers Cargo/pyproject/go.mod/
   package.json → registro de gates por ecosistema con PASS/FAIL/SKIP +
   `--strict-tools`; table estilo `gate.rs`; exits 0/1/2), y
   `drift` (port de `baseline_check.py`: manifiesto SHA-256 **implementado
   en la crate** (FIPS + vectores KAT), diff con fast-path size+mtime,
   `check|update`, exits 0/1/2).
2. **FR-XT2 — Sin artefactos Python en el baseline**: se eliminan
   `scripts/*.py`, `tests/*.py` y `pyproject.toml`; tests (unit + oráculo
   naïve + N/2N/4N + mutantes) viven en `xtask/src/**` con `cargo test`;
   el registro universal para repos Python/Go/web queda como **datos** en
   `check` y como tabla de comandos en `docs/gates.md`.
3. **FR-XT3 — ratchet decrease-only** `quality_baseline.json` (escrito por
   `cargo xtask`): subir violaciones ⇒ `ratchet` exit 1 y `--update-baseline`
   lo niega (exit 2) — política "sube solo con medición real" de CQE.
4. **FR-XT4 — trazabilidad AC↔citación** `cargo xtask trace`: regex
   `AC-[A-Z]{2,5}\d+` sobre `docs/specs/*.md` (sin `*TEMPLATE*`) e índice
   invertido de citas en `src/ tests/` de la workspace; AC nuevo sin cita ⇒
   exit 1 (`--strict-new`); `--update-baseline` congela el conocido.
5. **FR-XT5 — ejemplos universales** `docs/gates.md`: tabla por lenguaje con
   comandos y política de ratchets citando las fuentes del research
   (Rust: workspace.lints + `#[expect]` + cargo-mutants; Python: ruff +
   `fail_under`; Go: golangci `--new-from-rev`; Web: tsc+eslint
   `--max-warnings 0`).
6. **FR-XT6 — coherencia 11.75**: `docs/specs/TEMPLATE.md` exige formato
   `AC-<SIGLA><n>` (alimenta a `trace`); README/AGENTS/CI/CHANGELOG del
   baseline actualizados (CI añade job Rust: fmt+clippy+test).

## NF

- xtask std-only (0 crates.io ⇒ build sin red); docstrings ES en Rust
  (`///` con Args/Returns); Python ≤30 líneas/fn; 0 `except` silenciosos;
  sin rutas personales; UTF-8 sin BOM; 0 `.bat/.ps1/.cmd/.sh`.

## Exit criteria (gate)

- [ ] RED→GREEN en Rust: `cargo test` con la API sin implementar falla
      (E0425 ×15, citado) y tras implementar pasa.
- [ ] `cargo test` del workspace: ≥35 tests,0 fallos; **≥5 mutantes killed**
      con harness en Rust (copia mutada + `cargo test` anidado, control verde);
      `cargo clippy --workspace --all-targets -- -D warnings` y
      `cargo fmt --all --check` en0.
- [ ] Medición N/2N/4N en Rust: `drift` lecturas lineales exactas
      (`ops(4N)/ops(N)==4`) vs oráculo naïve Θ(L·A) (`≈16`) + KAT SHA-256;
      `ciclos` cadena N ⇒ ops = 2N−1.
- [ ] `cargo xtask gate` EXIT 0 con tabla citada; `cargo xtask check
      --strict-tools` y `cargo xtask drift check` EXIT 0.
- [ ] Ratchet: subida ⇒ `ratchet` exit1 y `--update-baseline` exit2
      (testeados); bajada congela suelo; `trace --strict-new` exit1 sin cita.
- [ ] Sin artefactos Python en el baseline (scripts/*.py, tests/*.py,
      pyproject.toml retirados) y docs/ejemplos en Rust.
- [ ] SWARMIND: `pytest harness/tests -q` 0 failed + batería completa
      (ruff/vulture/arquitectura+complejidad+rachets/preview/pep649/skills)
      verdes; docs ciclo (CHANGELOG 11.75+11.76, roadmap, MEJORAS, ADR);
      commit convencional y `publish.py`.

**No aplicado (declarado)**: cobertura ≥80 por tool (grcov/llvm-cov no está
en la toolchain local; sustituto: clippy + KAT + mutantes + oráculos;
queda en roadmap), port de `figures/msrv/shear/mutation-campaign` de CQE.

## Rollback

Revertir los commits de docs en SWARMIND; en el baseline, borrar
`xtask/`, `Cargo.toml`, `.cargo/`, `architecture.toml`,
`scripts/quality.py`, `quality_baseline.json`, `docs/gates.md` y los tests
nuevos; 11.75 queda intacto.
