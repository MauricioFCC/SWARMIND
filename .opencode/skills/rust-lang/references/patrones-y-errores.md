# Patrones Rust, Organigrama y Errores Comunes — detalle bajo demanda

> Migrado a `references/` por politica "focused beats comprehensive" (SkillsBench 2026).
> El indice accionable (3 pilares, guardrails y checklist) permanece en `SKILL.md`;
> aqui vive el detalle de principios, roles, patrones y errores del compilador.

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
