---
name: rust-lang
domain: systems
description: "Usar cuando el usuario programa en Rust o necesita sistemas seguros. ownership, borrowing, lifetimes, async, crates, optimizacion, sistemas concurrentes. Alcance: Rust y sistemas seguros; para arquitectura de sistemas ver architecture. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---

# Rust-lang (min)

## Los 3 Pilares (ESENCIA)
- 🔒 **Memory Safety**: Ownership + Borrowing garantizan ausencia de use-after-free/dangling en compile-time. `unsafe` sin `// SAFETY:` → BLOCK.
- ⚡ **Zero-Cost Abstractions**: abstracciones sin runtime overhead; alloc heap innecesario → WARN.
- 🧩 **Fearless Concurrency**: Send + Sync previenen data races en compile-time; `unsafe impl Send` sin auditoria → BLOCK.

## Patrones esenciales
- **RAII**: el recurso se libera al salir de scope (`File::open("x")?`).
- **Borrow Checker**: 1 `&mut T` XOR N `&T`, verificado en compile-time.
- **Errores**: `Result<T, E>` + `?`; `thiserror` (libraries), `anyhow` (apps).
- **Async**: Tokio (produccion, multi-thread), Smol (minimal/WASM), async-std.

## Ejemplo (borrow + Result, sin clone ni unwrap)
```rust
use std::collections::HashMap;

fn count_words(text: &str) -> HashMap<&str, usize> {
    let mut counts = HashMap::new();
    for w in text.split_whitespace() {
        *counts.entry(w).or_insert(0) += 1; // presta &str, no clona
    }
    counts
}

fn main() -> std::io::Result<()> {
    let content = std::fs::read_to_string("input.txt")?; // '?' propaga el error
    println!("palabras unicas: {}", count_words(&content).len());
    Ok(())
}
```

## Guardrails (HARD)
- `unsafe` sin `// SAFETY:` o `std::mem::transmute` → BLOCK.
- `Mutex` sync cruzando `.await` → BLOCK (usar `tokio::sync::Mutex`).
- `unwrap()` en produccion / dependencia sin `cargo audit` → WARN.

## Comandos
- `cargo check/build/test/clippy/fmt` — ciclo de desarrollo Rust
- `cargo flamegraph` — perfilado de CPU; `cargo audit` — seguridad de dependencias
- `maturin build/publish` — wheels Python; `wasm-pack build` — WASM

## Checklist
- [ ] Ownership/borrowing resuelto sin unsafe innecesario
- [ ] Errores con Result (sin panic en libreria)
- [ ] Concurrencia segura (Send/Sync, sin data races)
- [ ] clippy/fmt sin warnings
- [ ] FFI con Python acotado y seguro

## Referencias (bajo demanda)
- [Patrones Rust, organigrama y errores](references/patrones-y-errores.md)
- [Performance y FFI](references/performance-y-ffi.md)
- [Crates y comandos](references/crates-y-comandos.md)
