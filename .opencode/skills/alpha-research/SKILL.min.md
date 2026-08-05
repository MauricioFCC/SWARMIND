---
name: alpha-research
description: "Investigación de alpha — factores, ML avanzado, feature engineering y validación estadística con motores cuantitativos (ej. CQE Rust) | UPG·NAM·FRS (reglas en base_principles.md)"
---

## 🧪 Factor Zoo (`domain::models::factor_zoo`)

use quant-engine::domain::models::factor_zoo::{
    FactorDefinition, FactorZoo, FactorType,
    momentum::{MomentumFactor, TrendFactor},

### Pipeline de factores

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

use quant-engine::domain::ml::{
    causal::CausalDiscovery,
    conformal::ConformalPredictor,

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

use quant-engine::domain::validation::{
    performance::PerformanceMetrics,
    cv::CrossValidator,

### Anti-overfitting system 🛡️

### Deflated Sharpe Ratio (DSR)
fn compute_dsr(strategies: &[StrategyReturns], n_trials: usize) -> f64 {
    let max_sr = strategies.iter()
        .map(|s| PerformanceMetrics::sharpe_ratio(s))

## 🎯 Portfolio Construction (`domain::portfolio_risk`)

use quant-engine::domain::portfolio_risk::{
    portfolio::PortfolioOptimizer,
    risk::RiskModel,

### NCO (Nested Clustered Optimization)
let nco = NCO::new(factor_returns, asset_returns)
    .cluster(method="hierarchical")
    .optimize(risk_model="shrunk_covariance")

## 🆕 Frontier 2026 — Alpha Discovery

### AlphaCFG — Gramatica Formal para Factores
use alpha_discovery::AlphaCFG;

// Descubrimiento automatico de factores alfa usando gramatica libre de contexto

### PIKAN — Portfolio Optimization con Física
use pikan::PIKANPortfolio;

// Reemplaza MLPs con Kolmogorov-Arnold Networks en actor y critic

### Actualizacion de Modelos — Tabla 2026
| Modelo | Uso | CQE Module | Performance | Paper |
|--------|-----|-----------|-------------|-------|
| AlphaCFG | Factor discovery | `alpha_discovery::AlphaCFG` | Supera SOTA búsqueda factores | arXiv:2601.22119 |
| PIKAN | Portfolio RL | `pikan::PIKANPortfolio` | +25-40% Sharpe vs DRL | arXiv:2602.01388 |
| KAN | Feature interaction | `kan::KolmogorovArnoldNetwork` | +10-15% vs MLP | arXiv:2404.19756 |
| Graph Transformer | Riesgo sistémico | `graph_transformer::GraphTransformer` | +20-30% vs PCA | NeurIPS 2023 |
| Mamba SSM | Long time series | `mamba::MambaSSM` | +15-25% vs LSTM | ICML 2024 |
| Neural CDE | Irregular series | `neural_cde::NeuralCDE` | +12-18% vs RNN | NeurIPS 2022 |
| PCMCI | Causal discovery | `pcmci::PCMCI` | Precursor causal | Science 2019 |
| Conformal | Prediction intervals | `conformal::ConformalPredictor` | Cobertura 95% | JRSS-B 2023 |

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
