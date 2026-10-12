# Crates y Comandos — detalle bajo demanda

> Migrado a `references/` por politica "focused beats comprehensive" (SkillsBench 2026).
> El ciclo de desarrollo esencial permanece en `SKILL.md`; aqui vive el catalogo
> de crates recomendados y la referencia completa de comandos (cargo/FFI/WASM).

## 📦 CRATES RECOMENDADOS POR CATEGORIA

| Categoria | Crates |
|-----------|--------|
| **Async Runtime** | `tokio` (produccion), `smol` (minimal), `async-std` (std-like) |
| **Web Frameworks** | `axum` (moderno, tower-based), `actix-web` (actor, maduro), `rocket` (ergonomico) |
| **Serializacion** | `serde` + `serde_json`, `bincode` (binario), `rmp-serde` (msgpack), `prost` (protobuf) |
| **Logging** | `tracing` (estructurado, async-aware), `log` (facade), `env_logger` |
| **CLI** | `clap` (derive), `structopt` (legacy), `ratatui` (TUI) |
| **Testing** | `criterion` (bench), `quickcheck` / `proptest` (property-based), `test-case`, `rstest` |
| **FFI** | `pyo3` (Python), `wasm-pack` / `wasm-bindgen` (WASM), `cc` (C), `napi-rs` (Node) |
| **Data Structures** | `smallvec`, `arrayvec`, `hashlink`, `im` (persistent), `slotmap` |
| **Concurrency** | `crossbeam`, `rayon` (data parallelism), `parking_lot` (mutex mas rapido) |
| **Error Handling** | `thiserror` (librerias), `anyhow` (aplicaciones), `eyre` (reportes detallados) |
| **Parsing** | `nom` (combinator), `pest` (PEG), `winnow` (evolucion de nom) |

## 🧠 COMANDOS

### Desarrollo
- `cargo new <name>` — Nuevo proyecto
- `cargo build` / `cargo build --release` — Compilar
- `cargo check` — Check rapido sin generar binario
- `cargo test` — Ejecutar tests
- `cargo bench` — Ejecutar benchmarks
- `cargo clippy` — Linter con reglas de estilo y correccion
- `cargo fmt` — Formatear codigo
- `cargo doc --open` — Documentacion local

### Analisis
- `cargo udeps` — Detectar dependencias no usadas
- `cargo audit` — Vulnerabilidades de seguridad en dependencias
- `cargo-outdated` — Dependencias desactualizadas
- `cargo-expand` — Expandir macros
- `cargo-llvm-lines` — Tamaño de codigo generado por funcion

### Performance
- `cargo flamegraph` — Flamegraph de CPU
- `cargo profiler` — Perfilado con perf
- `cargo asm` — Ver assembly generado
- `cargo bloat` — Analisis de tamanio de binario

### FFI
- `maturin build` — Compilar wheel Python
- `maturin publish` — Publicar a PyPI
- `wasm-pack build` — Compilar a WASM
- `cbindgen` — Generar headers C desde Rust

## Nota de alcance

> 💡 **Nota**: Este skill complementa a hedgefund, quant-trading y risk-execution. Rust es el lenguaje de implementacion para sistemas de baja latencia, alta concurrencia y mision critica. Todo codigo Rust debe cumplir con los principios universales de base_principles.md.
