---
name: quant-trading
domain: trading
description: "Usar cuando el usuario implementa estrategias cuantitativas. trading, quant, baja latencia, alpha, motores cuantitativos, backtesting, market data. Alcance: implementacion del motor sobre CQE; para validacion de factores ver alpha-research. Cuando NO usar: ver Alcance. | UPG-NAM-FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---

# Quant-Trading (min)

Motor cuantitativo de alto rendimiento (Rust + bindings Python): barras,
features, senales, indicadores, ML y backtesting. Estrategia con edge
cuantificado, costes (fees/slippage) y test out-of-sample.

## Modulos del motor
- `domain::data_processing` (BarBuilder, FeatureExtractor) | `domain::signal_processing` (normalize, combine_signals, RegimeDetector)
- `domain::indicators` (SMA/EMA/HMA, RSI, ATR, VPIN) | `domain::ml` (FeatureStore) | `domain::backtesting` (BacktestEngine, PerformanceMetrics)

## Reglas
- Tipos del motor (`Trade`, `Quote`, `Order`, `Signal`), no genericos.
- NUNCA `unwrap()` en hot path -> `Result`/`expect`.
- Backtest con slippage/fees; walk-forward (min ratio 0.8) contra overfitting.
- Kelly para sizing; stop automatico si drawdown > max_dd.
- NUNCA loguear API keys/tokens.

## Checklist
- [ ] `cargo bench` + `cargo test --features=strict` antes de merge
- [ ] Memory: `cargo miri`; Fuzz: `cargo fuzz` en parsing de market data
- [ ] SIMD verificado con `cargo asm`; bindings `maturin build --release`
- [ ] Backtest con costes + out-of-sample; sizing Kelly; limite de drawdown
