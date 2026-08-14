---
name: rust-lang
domain: systems
description: "Usar cuando el usuario programa en Rust o necesita sistemas seguros. ownership, borrowing, lifetimes, async, crates, optimizacion, sistemas concurrentes. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---

# Rust-lang (min)

## Responsabilidades
- Diseno systems-level seguro con ownership/borrowing y fearless concurrency
- Implementacion de servidores async con tokio, smol o async-std
- FFI seguro con Python (PyO3/maturin), WASM (wasm-pack), C (cbindgen)
- Optimizacion de performance (perf, flamegraph, LTO, cache locality)
- Testing basado en propiedades (quickcheck, proptest) y benchmarks (criterion)

## Comandos
- `cargo check/build/test/clippy` — Ciclo de desarrollo Rust
- `cargo flamegraph` — Perfilado de CPU
- `cargo audit` — Auditoria de seguridad en dependencias
- `maturin build/publish` — Compilar/publicar wheels Python
- `wasm-pack build` — Compilar a WASM
