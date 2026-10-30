# Spec — Soporte de restructuración arquitectónica CQE (workspace multi-crate)

> Estado: proposed — Dueño: harness/orchestrator — Frontera: 2026-10-30.
> Espec generado tras 2 roundtables de investigación (kernel + complejidad +
> expatriación de `crates/*`). Contexto: `C:\Users\USUARIO\Documents\DEV-SPACE\core-quant-engine`.

## 1. Proposal

El kernel SWARMIND (scripts/harness) apoya la reestructuración de CQE desde un
monolito `core-quant-engine` (~250.000 LOC en `src/domain/**`, 6.9k tests) a un
workspace hexagonal multi-crate `cqe-*`. La extracción es机制, **strangler-fig**
con shims de reexport y guard = kata en CI, no `grep`. La ola 1-2 konkret
(`cqe-core`, `cqe-time`) se ejecutó; resta partir `cqe-math` (bloqueado por
`stats::adf_test`→`signal_processing`), `cqe-microstructure`, `cqe-indicators`,
`cqe-signals` y OMS/execution/backtest, con gates por crate.

### 1.1 Hallazgos adicionales (research 2025-2026)

- [matklad.github.io 2021](https://matklad.github.io/2021/08/22/large-rust-workspaces.html) —
  workspace flat `crates/*` + virtual manifest + `workspace.package/deps`,
  referentes Ruff (32 crates, 200k LOC, `publish=false`) y Polars (~20 crates).
- [github.com/zenide/cargo-crate-split](https://github.com/zenide/cargo-crate-split)
  — análisis de SCC con rank-acíclo y coste, propone el orden de extracción
  (herramienta de may-2026, **prometedora pero no battle-tested**).
- **strangler-fig**: [martinfowler.com/bliki/StranglerFigApplication.html]().
- **Facade como transición** (Bevy: `bevy` reexports `bevy_ecs`).
- **cargo-rubric** [github.com/joshfinley](https://github.com/joshfinley/rubric)
  para trazabilidad spec→test con atributos `#[satisfies(...)]`.
- [cargo hakari](https://docs.rs/cargo-hakari/latest) — workspace-hack de
  Facebook/guppy; 100x `cargo check` monocrate vs ~1.7x multiples.
- [cargo-nextest archive/partition](https://nexte.st/docs/ci-features/partitioning)
  (`--partition hash:m/n`) — mejora partición de suite sin binarios.
- [cargo-coverage-gate](https://docs.rs/cargo-coverage-gate/latest) — baseline
  de cobertura por crate en `[package.metadata.coverage-gate]`.
- [ArchUnitRust](https://github.com/LukasNiessen/ArchUnitRust) — capas en tests
  `cargo test --test architecture`.
- [rust-code-analysis](https://mozilla.github.io/rust-code-analysis/metrics.html) —
  métricas (CC, COGNITIVE, HALSTEAD, MI) por función.

## 2. Requirements (criterios de aceptación medibles)

| AC | Criterio |
|---|---|
| AC-CQE-RE1 | **Seam inventory** en `cargo-crate-split` actúa como fuente de verdad (no solo corte manual); entrega lo extraíble, la SCC y el orden. |
| AC-CQE-RE2 | **1 PR por crate extraído** (aislado con `CARGO_TARGET_DIR`), 0fix battery verde, guard `architecture.toml` en 0. |
| AC-CQE-RE3 | El crate raíz `core-quant-engine` **reexports** `cqe-core`/`cqe-time`/`cqe-math` hasta cerrar la ola (shim de transición, patrón Bevy). |
| AC-CQE-RE4 | **cqe-math se extrae con puertos** (dependency inversion): el paquete `math::stats::adf` delega llamadas, deforma a `signal_processing::signal::augmented_dickey_fuller_full`; extraer la matemática tomando `math::ols::ols_fit` y *no* `signal_processing` (la idea ya estaba en P3; implementarla). |
| AC-CQE-RE5 | Cada crate entra con su propio gate: `hakari`, `nextest --partition hash::m/n`, `coverage-gate` con baseline [package.metadata.coverage-gate] (no 100 % default), `archunit-rust` para capas, `iai-callgrind` con ratio N/2N < 2.4. |
| AC-CQE-RE6 | El **número** de tests no baja: cargo-nextest partition corre 6.9k/7k tests en tiempo exacto (~30 s) con的速度 simultánea y una suite combinada (sin gate singleton). |
| AC-CQE-RE7 | Ratchet de `dead_code_allows = <count>` decae (ADR-0090, `tests/agr_baseline.txt`). |
| AC-CQE-RE8 | **Spec-kit** (GitHub Spec Kit `/specify→/plan→/tasks`) aplicado a las olas 3-6: cada ola inicia con una spec cuantitativa y contract de éxito medible. |

## 3. Design

### 3.1 Del monolito al kernel (extracto adicional)

La ola 4.5 requiere un kernel event-driven. SWARMIND soporta la decisión con 4
crates: `cqe-bus` (pub/sub por topic + `Any` routing, correlation_id, handler
buffers), `cqe-cache` (write-through), `cqe-kernel` (single-loop determinista,
message + message bus, clock seam), `cqe-event-store` (captura en boundary,
`seq` asignada en writer thread con canal bounded). Para inbox/api/actors:

- `ractor-supervisor` con `OneForOne` / `RestForOne` en crates I/O;
  **no OneForAll** en el kernel (rompe el orden canónico).
- `kameo` si se necesita OTP out-of-the-box (bounded mailbox + supervision).
- `panic='abort'` para el kernel (crash-only) y `unwind` para crates I/O.

### 3.2 Gate de complejidad (in-stride N/2N/4N)

Cada crate extraído declara su benchmarking con un ratio Ir por N no excediendo
*lineal underside*; el spec `o-n-2-hotspots-gate.md` da las fórmulas.
Hotspots CQE a perseguir primero (basados en 43 módulos):

| Área | Tamaño | Fórmula a aplicar | Complejidad target |
|---|---|---|---|
| microstructure/indicators | 23k LOC | rolling O(1) por barra, Fenwick tree | O(LOG) |
| signal_processing | 18k LOC | Wilder/SMMA, KAMA, CVD/prefix-sums | O(1) por barra |
| models | 27k LOC | prefix-sums, Karp-Rabin, hash exacto | O(n+m) |
| backtesting | 16k LOC | event-driven con arena/pool prefetch | O(T) no recompilando |
| portfolio_risk | 18k LOC | Welford rolling + Cholesky rank-1 O(n²+O(n)) | O(nk) |
| validation | 8k LOC | Granger/ADF con QR-update O(mn) | O(nk) |
| execution | 12k LOC | Almgren-Chriss O(H), convolución por wave | O(H log H) |
| ml | 46k LOC | streaming continual (reservoir) O(1) | O(1) |
| data_processing | 14k LOC | Arrow 60 zero-copy, SoA stack vectorization | O(n) |
| live | 9k LOC | bounded MPSC + fail-stop threshold | O(log T) |

## 4. Referencias (resumen compuesto)

- [matklad.github.io](https://matklad.github.io/2021/08/22/large-rust-workspaces.html)
  (Large Rust Workspaces, 2021).
- [github.com/zenide/cargo-crate-split](https://github.com/zenide/cargo-crate-split)
  (may-2026).
- [martinfowler.com/bliki/StranglerFigApplication.html](https://martinfowler.com/bliki/StranglerFigApplication.html).
- [docs.rs/cargo-hakari/latest](https://docs.rs/cargo-hakari/latest).
- [nexte.st/docs/ci-features/partitioning](https://nexte.st/docs/ci-features/partitioning).
- [docs.rs/cargo-coverage-gate/latest](https://docs.rs/cargo-coverage-gate/latest).
- [github.com/LukasNiessen/ArchUnitRust](https://github.com/LukasNiessen/ArchUnitRust).
- [github.com/joshfinley/rubric](https://github.com/joshfinley/rubric) (abr-2026).
- [docs.rs/crate/archunit/latest](https://docs.rs/archunit/latest/archunit).
- [developer.microsoft.com/blog/spec-driven-development-spec-kit](https://developer.microsoft.com/blog/spec-driven-development-spec-kit/)
  (sep-2025).
- [doi:10.1016/j.infsof.2024.107590](https://doi.org/10.1016/j.infsof.2024.107590)
  — límite académico: pocas herramientas públicas y sin métricas.
