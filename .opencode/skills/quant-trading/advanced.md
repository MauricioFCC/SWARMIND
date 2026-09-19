# quant-trading — Advanced

> Detalle operativo y avanzado.

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

## 🆕 Frontier 2026 — Nuevas Tecnicas Incorporadas

### AlphaCFG — Grammar-Guided Alpha Discovery
```rust
// Descubrimiento automatico de factores alfa via gramatica formal
use alpha_discovery::AlphaCFG;

let cfg = AlphaCFG::new()
    .terminal_set(&["close", "volume", "high", "low", "returns"])
    .operator_set(&["+", "-", "*", "/", "lag", "rank", "ts_mean"])
    .max_depth(5);
let factors = cfg.discover(returns_data, n_factors=50)
    .mcts(iterations=10000)
    .evaluate(metric="rank_ic");
// Cada factor es un arbol sintactico valido, interpretable y computable
// Reference: arXiv:2601.22119 — AlphaCFG (Jan 2026)
```

### PIKAN — Physics-Informed KAN para Portfolio
```rust
// Reemplaza MLPs con KANs + fisica financiera
use pikan::PIKANPortfolio;

let pikan = PIKANPortfolio::new()
    .kan_layers(&[64, 32, 16])  // Kolmogorov-Arnold Networks
    .spline_degree(3)
    .physics_regularization(0.1)  // Regularizacion con leyes de Newton financieras
    .rl_algorithm("SAC");  // Soft Actor-Critic
// Reference: arXiv:2602.01388 — PIKAN (Feb 2026)
// Resultado: +15-25% Sharpe vs DRL clasico en mercados emergentes+desarrollados
```

### RL-Enhanced Static Analysis
```rust
// RL agent aprende a suprimir falsos positivos en analisis estatico Rust
// Combinado con cargo-fuzz para validacion dinamica
// Reference: arXiv:2605.04000 — RL for False Positive Mitigation (May 2026)
// Precision: 25.6% -> 59.0%, F1: 0.659 (+17.1% vs LLM baseline)
```

### Frontier — Vanguardia Implementada
- **KAN** networks para feature interaction
- **GNN** para riesgo sistemico
- **CubeCL** para GPU compute nativo Rust
- **WASM** para browser-based backtesting

