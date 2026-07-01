# skill: rust-leptos
**Dominio**: Rust + Leptos (SSR/WASM)
**Tech Stack**: Rust + Leptos + SurrealDB
**Patrones comunes**:
- Leptos con `cx: Scope` y señales `create_signal`, `create_resource`
- SurrealDB con `surrealql` y `sqlx`-style queries
- WASM build con `trunk` o `cargo-leptos`
- Axum como backend server
**Anti-patrones**:
- NO mezclar lógica server/client sin `#[server]`/`#[component]`
- NO usar `unwrap()` en producción
- NO shared state sin `Arc<RwLock<>>`
