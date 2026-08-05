---
name: quant-trading
description: "Estrategias cuantitativas de trading con motores cuantitativos de alto rendimiento (ej. quant-engine en Rust) — prioriza rendimiento, baja latencia y generación de alpha | UPG·NAM·FRS (reglas en base_principles.md)"
---

## 📡 Data Processing (`domain::data_processing`)

use quant-engine::domain::data_processing::{
    bars::{BarBuilder, BarType, TimeBar, VolumeBar, TickBar, DollarBar},
    features::FeatureExtractor,

### Flujo de datos para alpha

### Performance

## 📈 Señales (`domain::signal_processing`)

use quant-engine::domain::signal_processing::{
    signal::{Signal, SignalType, normalize, combine_signals, alpha_decay},
    regime::RegimeDetector,

### Pipeline de señales para alpha

### Alpha boosters 🚀

## 📊 Indicadores (`domain::indicators`)

use quant-engine::domain::indicators::{
    moving_averages::{SMA, EMA, WMA, HMA, ZLEMA, ALMA, KAMA, FRAMA, VIDYA},
    momentum::{RSI, MFI, Stochastic, WilliamsR, TSIFloor, ROC, TRIX, CCIMomentum},

### Selección de indicadores por régimen
| Régimen | Indicadores primarios | Parámetros |
|---------|----------------------|-------------|
| Trending | HMA, KAMA, FRAMA, MACD | Fast: 12/26, Slow: 50/200 |
| Mean-reverting | Bollinger, RSI, Stochastic | BB: 2.0σ, RSI: 14 periods |
| High volatility | ATR, VPIN, VolTarget | VPIN: 50 buckets |
| Low volatility | ZLEMA, Fisher, Coppock | Fisher: 9 periods, smooth: 3 |

### Implementación en Rust (SIMD)
// Ejemplo: EMA vectorizada con SIMD
fn ema_simd(data: &[f64], period: usize) -> Vec<f64> {
    let alpha = 2.0 / (period as f64 + 1.0);

## 🧠 Machine Learning (`domain::ml`)

use quant-engine::domain::ml::{
    features::FeatureStore,
    causal::CausalInference,

### Feature Store para alpha

## 📐 Backtesting (`domain::backtesting`)

use quant-engine::domain::backtesting::{
    engine::BacktestEngine,
    metrics::PerformanceMetrics,

### Workflow de backtesting

## 🆕 Frontier 2026 — Nuevas Tecnicas Incorporadas

### AlphaCFG — Grammar-Guided Alpha Discovery
// Descubrimiento automatico de factores alfa via gramatica formal
use alpha_discovery::AlphaCFG;

### PIKAN — Physics-Informed KAN para Portfolio
// Reemplaza MLPs con KANs + fisica financiera
use pikan::PIKANPortfolio;

### RL-Enhanced Static Analysis
// RL agent aprende a suprimir falsos positivos en analisis estatico Rust
// Combinado con cargo-fuzz para validacion dinamica
// Reference: arXiv:2605.04000 — RL for False Positive Mitigation (May 2026)

### Frontier — Vanguardia Implementada

## ✅ CHECKLIST PRE-COMMIT (MOTOR CUANTITATIVO)
- [ ] Usar tipos del motor cuantitativo (`Trade`, `Quote`, `Order`, `Signal`) no tipos genéricos
- [ ] Benchmarks: `cargo bench` en módulo relevante antes de merge
- [ ] Memory: `cargo miri` para UB, `valgrind` para leaks en hot path
- [ ] Fuzz: `cargo fuzz` en parsing de market data
- [ ] Tests: `cargo test --features=strict` antes de commit
- [ ] SIMD: verificar autovectorización con `cargo asm`
- [ ] Python bindings: `maturin build --release` si hay cambios en API
- [ ] **NUEVO**: RL-based false positive suppression para Rust static analysis (arXiv:2605.04000)

## ⚠️ GUARDRAILS
