# Factor Zoo y ML Avanzado (APIs CQE) — detalle bajo demanda

> Migrado de `SKILL.md` a `references/` por política "focused beats comprehensive"
> (SkillsBench 2026, arXiv:2602.12670). El checklist de falsación y los umbrales
> de validación permanecen en `SKILL.md`; aquí vive el catálogo de factores y modelos.

## 🧪 Factor Zoo (`domain::models::factor_zoo`)

```rust
use quant-engine::domain::models::factor_zoo::{
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
use quant-engine::domain::ml::{
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
