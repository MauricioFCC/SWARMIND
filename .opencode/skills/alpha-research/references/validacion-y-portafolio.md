# Validación y Construcción de Portafolio — detalle bajo demanda

> Migrado de `SKILL.md` a `references/` por política "focused beats comprehensive"
> (SkillsBench 2026, arXiv:2602.12670). Los umbrales de decisión y el checklist
> permanecen en `SKILL.md`; aquí vive el detalle de APIs y código de validación.

## 📊 Validación (`domain::validation`)

```rust
use quant-engine::domain::validation::{
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
use quant-engine::domain::portfolio_risk::{
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
