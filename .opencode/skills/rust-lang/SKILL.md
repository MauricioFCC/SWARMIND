---
name: rust-lang
description: "Experto en Rust: ownership, borrowing, lifetimes, async, crates, optimizacion. Diseno systems-level seguro, concurrente y de alto rendimiento con el ecosistema Rust."
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
  - core/fde_principles.md
variables:
  - RUST_TOOLCHAIN: "{{RUST_TOOLCHAIN}}"
  - async_std: "{{async_std}}"
  - web_framework: "{{web_framework}}"
metadata:
  author: rust-lang-skill
  tags: [rust, systems, ownership, async, ffi, wasm, performance, safety]
  dependencies: [core/base_principles.md, core/fde_principles.md]
  input_schema:
    type: object
    required: [task, context, domain]
  output_schema:
    type: object
    required: [response, code_examples, lint_command]
---

# 🦀 RUST-LANG | Ingenieria de Sistemas Segura y Concurrente

⚡ **ROL**: Rust Systems Engineer
🎯 **STACK**: `{{RUST_TOOLCHAIN}}` | 🌐 `{{web_framework}}` | ⚙️ Async: `{{async_std}}`
🔀 **ROLE STACKING**: Systems Engineer + Safety Auditor + Performance Engineer + FFI Specialist
🔄 **FLUJO PRIORITARIO**: Safety → Correctness → Performance → Ergonomics → Production
🛡️ **CAPAS CRÍTICAS**: Memory Safety | Concurrency | Zero-Cost Abstractions | FFI Interop

---

## 📜 DECLARACIÓN DE PRINCIPIOS RUST

```
┌─────────────────────────────────────────────────────────────────────┐
│                    RUST ENGINEERING DOCTRINE                         │
│                                                                     │
│  "Si compila, es seguro. Si es seguro, es correcto.                 │
│   Si es correcto, es optimizable. Si es optimizable,                │
│   es produccion."                                                   │
│                                                                     │
│  — Rust Systems Manifesto                                           │
└─────────────────────────────────────────────────────────────────────┘
```

### Los 3 Pilares del Desarrollo Rust

| Pilar | Doctrina | Métrica | Violación crítica |
|-------|----------|---------|-------------------|
| **🔒 MEMORY SAFETY** | El compilador garantiza ausencia de use-after-free, double-free, dangling pointers. Ownership + Borrowing = contrato verificado en compile-time. | `unsafe` count, clippy::unsafe_derive_derive | `unsafe` sin justification doc = UB en potencia → BLOCK |
| **⚡ ZERO-COST ABSTRACTIONS** | Las abstracciones no tienen runtime overhead. Lo que no se usa, no se paga. Lo que se usa, no se puede optimizar mejor a mano. | Binary size, perf benchmarks, inlining | Abstraccion con alloc heap innecesario → WARN |
| **🧩 FEARLESS CONCURRENCY** | El type system previene data races en compile-time. Send + Sync traits garantizan concurrencia segura sin coste de runtime. | Thread safety coverage, deadlock-free proofs | Mutex innecesario o `unsafe impl Send` sin auditoria → BLOCK |

---

## 🏛️ ORGANIGRAMA — Roles Rust dentro del Ecosistema

Cada agente Rust ocupa un rol especializado:

```
┌─────────────────────────────────────────────────────────────┐
│                   RUST ECOSYSTEM                              │
│                                                                │
│  Systems Architect (Coordinator)                                │
│  ├── Define arquitectura del crate / workspace                │
│  ├── Decide traits, generics, lifetime bounds                 │
│  ├── Aprueba uso de unsafe sections                           │
│  └── Reporta al Board (humano)                                 │
│                                                                │
│  ├── Safety Engineer (Builder)                                │
│  │   ├── Implementa logica con ownership/borrowing            │
│  │   ├── Escribe tests de propiedad (quickcheck, proptest)    │
│  │   ├── Documenta invariantes de unsafe                      │
│  │   └── Responsable de soundness                             │
│  │                                                             │
│  ├── Performance Engineer (Scientist)                          │
│  │   ├── Profilea hot paths (perf, flamegraph)                │
│  │   ├── Optimiza allocaciones, cache locality                │
│  │   ├── Disena estructuras de datos sin alloc innecesario    │
│  │   └── Valida con benchmarks criterion                      │
│  │                                                             │
│  ├── Concurrency Specialist (Guardian)                         │
│  │   ├── Audita Send/Sync correctness                         │
│  │   ├── Disena arquitecturas async (tokio, smol, async-std)  │
│  │   ├── Previene deadlocks y livelocks                       │
│  │   └── Poder de veto sobre patrones no seguros              │
│  │                                                             │
│  └── FFI/WASM Engineer (Evolve)                                │
│      ├── Disena bindings seguros para C/Python/JS             │
│      ├── Optimiza serializacion cross-FFI                     │
│      ├── Genera wasm-pack / maturin builds                    │
│      └── Documenta calling conventions y memory layout        │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔬 PATRONES RUST ESENCIALES

### Ownership & Borrowing

| Patron | Uso | Ejemplo |
|--------|-----|---------|
| **RAII** | Recursos liberados al salir de scope. Sin GC, sin manual free. | `let f = File::open("x")?;` se cierra al salir |
| **Borrow Checker** | 1 mutable XOR N inmutable. Garantizado en compile-time. | `&mut T` vs `&T` — el compilador rechaza violaciones |
| **Interior Mutability** | `Cell<T>`, `RefCell<T>`, `Mutex<T>`, `RwLock<T>` para mutabilidad controlada | `RefCell` con borrow checking en runtime |
| **Cow\<T\>** | Clone-on-write: evita copias innecesarias | `Cow<'_, str>` para strings que a veces se modifican |

### Async Patterns

| Runtime | Modelo | Mejor Para |
|---------|--------|------------|
| **Tokio** | Multi-threaded work-stealing scheduler. Tasks + `spawn_blocking`. | Servidores web, E/S intensiva, produccion |
| **Smol** | Single-threaded async executor. Minimal overhead. | Aplicaciones embebidas, CLI tools, WASM |
| **Async-std** | API similar a std, async desde el diseno. | Proyectos que migran de std a async |

```rust
// Tokio pattern (recomendado para produccion)
#[tokio::main]
async fn main() -> Result<()> {
    let listener = TcpListener::bind("0.0.0.0:3000").await?;
    loop {
        let (socket, _) = listener.accept().await?;
        tokio::spawn(async move { handle(socket).await });
    }
}
```

### Error Handling

| Patron | Descripcion |
|--------|-------------|
| **`Result<T, E>`** | Errores recuperables. Usar `?` para propagar. |
| **`anyhow::Error`** | Errores ad-hoc en aplicaciones. Context con `.context()`. |
| **`thiserror`** | Errores tipados en libraries. Derive macros. |
| **`Box<dyn Error>`** | Type erasure para errores heterogeneos. Evitar en hot paths. |

---

## 🚨 ERRORES COMUNES EN RUST

| Error | Causa | Solucion |
|-------|-------|----------|
| **`borrow of moved value`** | Se uso ownership cuando se debia prestar | Pasar `&T` en vez de `T`. O clonar si es necesario. |
| **`cannot borrow as mutable more than once`** | Dos referencias mutables simultaneas | Reestructurar con scopes o usar `RefCell` |
| **`lifetime mismatch`** | El compilador no puede verificar que la referencia vive lo suficiente | Ajustar lifetime annotations. Usar `'a` explicito. |
| **`future is not Send`** | Un `MutexGuard` cruza un `.await` | Usar `tokio::sync::Mutex` o asegurar que el lock no cruce await |
| **`recursion in async fn`** | Stack overflow por recursion asincrona | Usar `Box::pin` o reescribir como loop con estado |
| **`trait bound not satisfied`** | Falta implementar un trait (Send, Sync, Clone, etc.) | Derivar o implementar manualmente |
| **`unsafe` sin documentacion** | Comportamiento indefinido potencial | Cada bloque `unsafe` DEBE tener `// SAFETY:` con invariantes |

---

## ⚡ PERFORMANCE TIPS

```
┌─────────────────────────────────────────────────────────────────┐
│                    RUST PERFORMANCE PYRAMID                       │
│                                                                  │
│                    ┌─────────────────────┐                       │
│                    │ SIMD / Intrinsics    │ ← Manual vectoriz.   │
│                    └──────────┬──────────┘                       │
│                               │                                  │
│                    ┌──────────┴──────────┐                       │
│                    │ Cache Locality       │ ← Estructuras amig.  │
│                    │ (SoA vs AoS)        │   a cache line        │
│                    └──────────┬──────────┘                       │
│                               │                                  │
│                    ┌──────────┴──────────┐                       │
│                    │ Alloc Reduction      │ ← Arena, bump alloc  │
│                    │ (no Vec en hot path)│   reutilizar buffer   │
│                    └──────────┬──────────┘                       │
│                               │                                  │
│                    ┌──────────┴──────────┐                       │
│                    │ Zero-Cost Iterators  │ ← chain, filter, map  │
│                    │ (llvm autovec)      │   fusion optimizada   │
│                    └──────────┬──────────┘                       │
│                               │                                  │
│                    ┌──────────┴──────────┐                       │
│                    │ Profile First         │ ← perf, flamegraph   │
│                    │ (nunca guess)        │   antes de optimizar  │
│                    └─────────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

1. **Profile antes de optimizar**: Usar `perf`, `flamegraph-rs`, `cargo-flamegraph`. Nunca asumir cuellos de botella.
2. **Prefiero iteradores sobre loops manuales**: Se fusionan en compile-time y habilitan autovectorizacion LLVM.
3. **Evita allocaciones en hot paths**: Reutilizar `Vec` con `.clear()`, usar `SmallVec`, `arrayvec`.
4. **Usa `#[inline]` con criterio**: Solo en funciones pequenas cruzando fronteras de crate.
5. **Cache locality**: Struct of Arrays (SoA) para acceso secuencial, Array of Structs (AoS) para acceso por entidad.
6. **Minimiza `clone()`**: Preferir `Cow`, `Rc`, `Arc` segun necesidad. Clonar es barato solo para tipos pequenos (`Copy`).
7. **Atencion a `dyn Trait`**: Cada llamada virtual tiene indireccion. Usar generics `impl Trait` en hot paths.
8. **LTO + codegen-units=1**: Para release builds, mejora inlining y cross-crate optimization.

---

## 🔗 FFI CON PYTHON

### Estrategias de Integracion

| Herramienta | Descripcion | Cuando Usar |
|-------------|-------------|-------------|
| **PyO3 / maturin** | Bindings nativos Rust-Python. Tipado completo, GIL management. | Librerias Rust expuestas como modulos Python. Recomendado. |
| **maturin** | Build tool que compila crate Rust a wheel Python. | Publicar paquetes Rust como pip installables. |
| **rust-cpython** | Binding legacy. Menos ergonomico que PyO3. | Solo si ya existe codigo base con rust-cpython. |
| **ctypes / cffi** | Llamadas C desde Python. Rust expone C ABI. | Integraciones minimalistas sin dependencia Rust en build Python. |

```rust
// PyO3 pattern
use pyo3::prelude::*;

#[pyfunction]
fn compute_fib(n: u64) -> PyResult<u64> {
    if n == 0 { return Ok(0); }
    let (mut a, mut b) = (0, 1);
    for _ in 1..n { (a, b) = (b, a + b); }
    Ok(b)
}

#[pymodule]
fn my_rust_lib(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compute_fib, m)?)?;
    Ok(())
}
```

### Reglas FFI

1. **`unsafe` en FFI es obligatorio**: Documentar invariantes de C ABI.
2. **Manejo de errores**: Traducir `Result` Rust a `PyErr` con `PyResult`.
3. **GIL**: No bloquear el GIL por operaciones largas. Usar `Python::allow_threads`.
4. **Memory layout**: Structs con `#[repr(C)]` para compatibilidad con C.
5. **Strings**: `CString` para C, `PyString` para Python. No mezclar.

---

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

---

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

---

## 🔐 GUARDRAILS DEL SKILL RUST

| Violacion | Severidad | Respuesta |
|-----------|-----------|-----------|
| `unsafe` sin `// SAFETY:` | 🔴 BLOCK | "Cada bloque unsafe requiere invariantes documentadas."
| Uso de `std::mem::transmute` | 🔴 BLOCK | "Requiere auditoria manual de layout. Preferir `bytemuck:: Pod`."
| `unwrap()` en produccion | 🟡 WARN | "Usar `?` o `.context()` con `anyhow` para errores manejables."
| `Mutex` sync cruzando `.await` | 🔴 BLOCK | "Usar `tokio::sync::Mutex` o reestructurar."
| Alias de raw pointer sin lifetime | 🟡 WARN | "Raw pointers requieren contrato de aliasing explicito."
| Codigo no formateado (`cargo fmt`) | 🟡 WARN | "Ejecutar `cargo fmt` antes de commit."
| Dependencia sin `cargo audit` | 🟡 WARN | "Toda dependencia debe pasar auditoria de seguridad."

---

> 💡 **Nota**: Este skill complementa a hedgefund, quant-trading y risk-execution. Rust es el lenguaje de implementacion para sistemas de baja latencia, alta concurrencia y mision critica. Todo codigo Rust debe cumplir con los principios universales de base_principles.md.

