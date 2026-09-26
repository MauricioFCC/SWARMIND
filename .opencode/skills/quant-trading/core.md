# quant-trading — Core

> Fundamentos. Detalle en `advanced.md`.

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
| High volatility | ATR, VPIN, VolTarget | VPIN: 50 buckets |
| Low volatility | ZLEMA, Fisher, Coppock | Fisher: 9 periods, smooth: 3 |

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

