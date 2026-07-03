---
name: alpha-research
domain: research
description: Investigación de alpha — factores, ML avanzado, feature engineering y validación estadística con CQE Rust
---

# Alpha Research — CQE Rust Engine

Investigación sistemática de alpha usando **core-quant-engine** (CQE).
Enfoque: falsificación de hipótesis nula, walk-forward, out-of-sample robusto.

## 🧪 Factor Zoo (`domain::models::factor_zoo`)

```rust
use core_quant_engine::domain::models::factor_zoo::{
    FactorDefinition, FactorZoo, FactorType,
    momentum::{MomentumFactor, TrendFactor},
    value::{BookToMarket, EarningsYield, CashFlowYield},
    quality::{ROE, ROA, Profitability, Accruals},
    size::{MarketCap, MicroCap},
    low_beta::{Beta, VolatilityFactor, TailRisk},
    seasonal::SeasonalFactor,
    sentiment::SentimentFactor,
};
```

### Pipeline de factores
1. `FactorDefinition::new("alpha_101", FactorType::Momentum)` → define factor
2. `FactorZoo::compute_all(data, &[factors])` → 101+ factores en paralelo
3. `FactorZoo::neutralize(market_cap, sector)` → neutralizar por tamaño/sector
4. `FactorZoo::orthogonalize()` → Gram-Schmidt para factores correlacionados
5. `FeatureImportance::shap_values(model, factors)` → SHAP values

### Factores con mayor alpha histórico en CQE
| Factor | Tipo | CQE Module | Half-life | Sharpe (anualizado) |
|--------|------|-----------|-----------|-------------------|
| Momentum 12-1 | Mom | `FactorZoo::momentum_12_1()` | 6 meses | 0.8-1.2 |
| Value (E/P) | Val | `FactorZoo::earnings_yield()` | 12 meses | 0.5-0.9 |
| Low Vol 60d | Risk | `FactorZoo::low_volatility()` | 3 meses | 0.6-1.0 |
| Quality (ROE) | Qlt | `FactorZoo::quality_roe()` | 12 meses | 0.7-1.1 |
| Short-term reversal | Mom | `FactorZoo::short_term_reversal()` | 1 mes | 0.4-0.8 |
| Carry (FX) | Carry | `FactorZoo::carry()` | 3 meses | 0.5-0.9 |

## 🤖 ML Avanzado (`domain::ml`)

```rust
use core_quant_engine::domain::ml::{
    causal::CausalDiscovery,
    conformal::ConformalPredictor,
    copula::CopulaModel,
    denoising::DenoisingAutoencoder,
    diffusion::DiffusionModel,
    federated::FederatedLearning,
    foundation::FoundationModel,
    graph_neural::GraphNeuralNetwork,
    graph_transformer::GraphTransformer,
    kan::KolmogorovArnoldNetwork,
    mamba::MambaSSM,
    neural_cde::NeuralCDE,
    neural_sde::NeuralSDE,
    optimal_transport::OptimalTransport,
    pcmci::PCMCI,
    pinns::PINNs,
    quantum::QuantumModel,
    signature::SignatureMethod,
    synthetic::SyntheticData,
    xai::XAIExplainer,
    continual_learning::ContinualLearning,
};
```

### Modelos para alpha
| Modelo | Uso | CQE Module | Performance vs baseline |
|--------|-----|-----------|------------------------|
| Mamba SSM | Series temporales largas | `mamba::MambaSSM` | +15-25% vs LSTM |
| Graph Transformer | Riesgo sistémico | `graph_transformer::GraphTransformer` | +20-30% vs PCA |
| KAN | Feature interaction | `kan::KolmogorovArnoldNetwork` | +10-15% vs MLP |
| Neural CDE | Irregular time series | `neural_cde::NeuralCDE` | +12-18% vs RNN |
| PCMCI | Causal discovery | `pcmci::PCMCI` | Precursor de causalidad |
| Conformal | Prediction intervals | `conformal::ConformalPredictor` | Cobertura 95% calibrada |

## 📊 Validación (`domain::validation`)

```rust
use core_quant_engine::domain::validation::{
    performance::PerformanceMetrics,
    cv::CrossValidator,
    bootstrap::BootstrapTest,
    dataset_shift::DatasetShiftDetector,
    labeling::TripleBarrierLabeling,
    sample_weights::SampleWeights,
    backtest_overfitting::DeflatedSR,
};
```

### Anti-overfitting system 🛡️
1. `TripleBarrierLabeling::label(returns, barrier=2.0, time=20)` → labeling
2. `CrossValidator::purged_walk_forward(n_folds=5, purge=50)` → CV purgado
3. `BootstrapTest::sharpe_ratio(metric, n_iterations=10000)` → p-value del Sharpe
4. `DatasetShiftDetector::detect(in_sample, out_sample)` → detectar data snooping
5. `DeflatedSR::probability(expected_n=200)` → Probabilidad de SR ajustado por múltiples tests

### Deflated Sharpe Ratio (DSR)
```rust
fn compute_dsr(strategies: &[StrategyReturns], n_trials: usize) -> f64 {
    let max_sr = strategies.iter()
        .map(|s| PerformanceMetrics::sharpe_ratio(s))
        .fold(0.0, f64::max);
    DeflatedSR::probability(max_sr, n_trials)
}
// DSR > 0.95 → alpha real. DSR < 0.5 → probable sobreajuste.
```

## 🎯 Portfolio Construction (`domain::portfolio_risk`)

```rust
use core_quant_engine::domain::portfolio_risk::{
    portfolio::PortfolioOptimizer,
    risk::RiskModel,
    measures::RiskMeasures,
    nco::NCO,
    advanced::{
        mean_cvar::MeanCVAR,
        robust::RobustOptimization,
        online::OnlinePortfolio,
        factor_timing::FactorTiming,
    },
};
```

### NCO (Nested Clustered Optimization)
```rust
let nco = NCO::new(factor_returns, asset_returns)
    .cluster(method="hierarchical")
    .optimize(risk_model="shrunk_covariance")
    .compute();
```
El NCO de CQE supera a MV clásico en 2-3x Sharpe out-of-sample.

## ✅ CHECKLIST ALPHA RESEARCH
- [ ] Hipótesis nula definida ANTES de computar cualquier estadístico
- [ ] Walk-forward con 5 folds purgados (CV temporal)
- [ ] Sharpe ratio bootstrap con 10,000 muestras
- [ ] DSR (Deflated Sharpe Ratio) ajustado por múltiples tests
- [ ] Out-of-sample mínimo 30% del periodo total
- [ ] Costos de transacción incluidos (`slippage::SlippageModel`)
- [ ] Benchmark: buy & hold + igual-ponderado + risk-parity
- [ ] Feature importance: SHAP values + permutation importance
- [ ] Código en Rust para hot path, Python para prototipado
