# skill: rust-trading
**Dominio**: Trading Cuantitativo (Rust)
**Tech Stack**: Rust + Trading
**Patrones comunes**:
- Library pura sin runtime (no async)
- Feature flags para backtesting/live
- `Result<T, E>` en toda I/O, `anyhow` o `thiserror`
- NaN-safety en cálculos financieros
**Anti-patrones**:
- NO usar `f64` para dinero (usar decimal o i64 fixed-point)
- NO blocking I/O en hot paths
- NO unwrap en producción
