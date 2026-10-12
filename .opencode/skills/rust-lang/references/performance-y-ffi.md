# Performance y FFI — detalle bajo demanda

> Migrado a `references/` por politica "focused beats comprehensive" (SkillsBench 2026).
> El checklist y los guardrails permanecen en `SKILL.md`; aqui vive la piramide de
> performance, los tips de optimizacion y las reglas de FFI (ABI/PyO3).

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
