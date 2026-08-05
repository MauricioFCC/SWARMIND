---
name: quant-trading
description: "Estrategias cuantitativas de trading con quant-engine (CQE) en Rust — prioriza rendimiento, baja latencia y generación de alpha"
---

# Quant Trading — CQE Rust Engine
Estrategias cuantitativas implementadas sobre **quant-engine** (CQE) v2.1.0.
Stack: Rust 🦀 + Python bindings. Prioridad: rendimiento > legibilidad cuando hay trade-off.
## 📡 Data Processing (`domain::data_processing`)
```rust
use quant-engine::domain::data_processing::{
    bars::{BarBuilder, BarType, TimeBar, VolumeBar, TickBar, DollarBar},
    features::FeatureExtractor,
    robust_stats::RobustStats,
    quality::QualityScore,
    sanitization::Sanitizer,
    information_theory::{
        entropy, mutual_information, transfer_entropy,
        ConditionalEntropy, PartialTransferEntropy,
    },
    tda::TopologicalDataAnalysis,
    conformal_anomaly::ConformalAnomalyDetector,
};
```
### Flujo de datos para alpha
1. **Raw ticks** → `TickBar` / `TimeBar` / `VolumeBar` / `DollarBar` según instrumento
2. **Sanitización** → `Sanitizer::remove_outliers()` + `QualityScore::validate()`
3. **Features** → `FeatureExtractor::compute()` extrae 200+ features
4. **Robust stats** → `RobustStats::mean()` sobre mediana para resistir outliers
5. **Información teórica** → `transfer_entropy()` para causalidad entre activos
6. **TDA** → `TopologicalDataAnalysis::persistent_homology()` para regime change
### Performance
- SIMD activado vía `domain::math::simd`
- Procesamiento por batches de 10,000 ticks usando `alloc::Vec` pre-asignado
- Evitar cloning: usar `std::mem::take()` y `Arc<[T]>` para datos compartidos
## 📈 Señales (`domain::signal_processing`)
```rust
use quant-engine::domain::signal_processing::{
    signal::{Signal, SignalType, normalize, combine_signals, alpha_decay},
    regime::RegimeDetector,
    volatility::VolatilityEstimator,
    volatility_target::VolatilityTargeting,
    microstructure::MicrostructureFeatures,
    intraday::IntradayPatterns,
    changepoint::ChangepointDetector,
    hmm::HiddenMarkovModel,
    spectral::SpectralAnalysis,
    slippage::SlippageModel,
    trailing_stop::TrailingStop,
    point_processes::HawkesProcess,
    time_series::{
        arima::Arima,
        var::VectorAutoregression,
        state_space::KalmanFilter,
    },
};
```
### Pipeline de señales para alpha
1. **Regime detection** → `RegimeDetector::detect()` clasifica mercado en 4 regimes
2. **Volatility** → `VolatilityEstimator::adaptive_estimate()` con EWMA + HAR
3. **Microestructura** → `MicrostructureFeatures::compute()` para HFT signals
4. **Changepoint** → `ChangepointDetector::pelt()` para detectar cambios de régimen
5. **HMM** → `HiddenMarkovModel::viterbi()` para estados latentes
6. **Spectral** → `SpectralAnalysis::fft()` para ciclos y estacionalidad
7. **Combinación** → `combine_signals()` con peso dinámico por régimen
8. **Decaimiento** → `alpha_decay()` modelo de decaimiento exponencial
### Alpha boosters 🚀
- Vol target: `VolatilityTargeting::compute_position_size()` para sizing consistente
- Hawkes process: `HawkesProcess::fit()` para eventos de alta frecuencia
- Kalman filter: `KalmanFilter::online_update()` para estimación en tiempo real
- TVAR: `VectorAutoregression::time_varying()` para relaciones cambiantes
## 📊 Indicadores (`domain::indicators`)
```rust
use quant-engine::domain::indicators::{
    moving_averages::{SMA, EMA, WMA, HMA, ZLEMA, ALMA, KAMA, FRAMA, VIDYA},
    momentum::{RSI, MFI, Stochastic, WilliamsR, TSIFloor, ROC, TRIX, CCIMomentum},
    oscillators::{MACD, AO, AC, Bop, FisherTransform, Coppock},
    channels::{Bollinger, Keltner, Donchian, Envelope},
    volume::{OBV, ADL, CMF, VolumeProfile, VPIN},
};
```
### Selección de indicadores por régimen
| Régimen | Indicadores primarios | Parámetros |
|---------|----------------------|-------------|
| Trending | HMA, KAMA, FRAMA, MACD | Fast: 12/26, Slow: 50/200 |
| Mean-reverting | Bollinger, RSI, Stochastic | BB: 2.0σ, RSI: 14 periods |
| _... 2 more rows_ |
### Implementación en Rust (SIMD)
```rust
// Ejemplo: EMA vectorizada con SIMD
fn ema_simd(data: &[f64], period: usize) -> Vec<f64> {
    let alpha = 2.0 / (period as f64 + 1.0);
    let mut result = Vec::with_capacity(data.len());
    let mut ema = data[0]; // warmup
    result.push(ema);
    // Kernel SIMD para el cálculo
    for &price in data[1..].iter() {
        ema = alpha * price + (1.0 - alpha) * ema;
        result.push(ema);
    }
    result
}
// Usar: let fast = HMA::new(&data, 50); let slow = HMA::new(&data, 200);
```
## 🧠 Machine Learning (`domain::ml`)
```rust
use quant-engine::domain::ml::{
    features::FeatureStore,
    causal::CausalInference,
    copula::CopulaModel,
    clustering::ClusterModel,
    conformal::ConformalPredictor,
    denoising::DenoisingAutoencoder,
    feature_importance::FeatureImportance,
    loss_functions::WeightedHuber,
    linfa_wrapper::LinfaWrapper,
};
```
### Feature Store para alpha
1. `FeatureStore::register("momentum_1m", momentum_fn)` → feature computada
2. `FeatureStore::register("vol_20d", vol_fn)`
3. `FeatureStore::compute_all()` → 500+ features en paralelo (Rayon)
4. `FeatureImportance::permutation_importance()` → top-50 features
## 📐 Backtesting (`domain::backtesting`)
```rust
use quant-engine::domain::backtesting::{
    engine::BacktestEngine,
    metrics::PerformanceMetrics,
    vectorized::VectorizedBacktest,
    optimizer::WalkForwardOptimizer,
    attribution::AttributionAnalysis,
    distributed::DistributedBacktest,
};
```
### Workflow de backtesting
1. `VectorizedBacktest::new(strategy, data)` → vectorized first pass
2. `WalkForwardOptimizer::optimize(params, metrics)` → walk-forward CV
3. `BacktestEngine::run_event_driven(signal, execution)` → event-driven second pass
4. `PerformanceMetrics::compute(&trades)` → Sharpe, Sortino, Calmar, etc.
5. `AttributionAnalysis::decompose()` → PnL por factor, sector, instrumento
## ✅ CHECKLIST PRE-COMMIT CQE
- [ ] Usar tipos CQE (`Trade`, `Quote`, `Order`, `Signal`) no tipos genéricos
- [ ] Benchmarks: `cargo bench` en módulo relevante antes de merge
- [ ] Memory: `cargo miri` para UB, `valgrind` para leaks en hot path
- [ ] Fuzz: `cargo fuzz` en parsing de market data
- [ ] Tests: `cargo test --features=strict` antes de commit
- [ ] SIMD: verificar autovectorización con `cargo asm`
- [ ] Python bindings: `maturin build --release` si hay cambios en API
## ⚠️ GUARDRAILS
- NUNCA usar `unwrap()` en hot path de trading → usar `expect("context")` o `Result`
- NUNCA loguear API keys, tokens o secretos
- Position sizing: siempre validar contra `risk_management::BetSizing::kelly()`
- Slippage: siempre incluir `slippage::SlippageModel::estimate()` en backtests
- Overfitting: `WalkForwardOptimizer::min_ratio(0.8)` mínimo
- Drawdown: stop automático si `portfolio_risk::measures::drawdown() > max_dd`