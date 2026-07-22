---
name: rust-lang
domain: systems
description: "Rust systems engineering — ownership, borrowing, lifetimes, async runtimes (tokio, smol, async-std), web frameworks (axum, actix, rocket), FFI with Python via PyO3/maturin, performance optimization, cargo tooling"
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
