# Modelos de Riesgo (APIs CQE) — detalle bajo demanda

> Migrado de `SKILL.md` a `references/` por política "focused beats comprehensive"
> (SkillsBench 2026, arXiv:2602.12670). El índice accionable (sizing, límites,
> guardrails) permanece en `SKILL.md`; aquí vive el detalle de las APIs.

## 📐 Risk Management (`domain::risk_management`)

```rust
use quant-engine::domain::risk_management::{
    bet_sizing::{
        KellyCriterion, HalfKelly, QuarterKelly, 
        FixedFraction, VolatilityParity, ConfidenceWeighted,
    },
    evt::{
        EVTEstimator, GPD, BlockMaxima, PeaksOverThreshold,
    },
    meta_labeling::{
        MetaLabelingModel, Precision, Recall, F1,
    },
    multiple_testing::{
        FDR, Bonferroni, Holm, BenjaminiHochberg,
        NumberOfTrials,
    },
    gamblers_ruin::GamblersRuin,
};
```

### Extreme Value Theory (EVT)
```rust
// Modelar colas pesadas para tail risk
let evt = EVTEstimator::new(&returns)
    .method(ExtremeMethod::PeaksOverThreshold)
    .threshold(0.95)  // 95th percentile
    .fit();
let var_99 = evt.var(0.99);       // VaR 99% EVT
let es_975 = evt.expected_shortfall(0.975);  // CVaR 97.5% EVT
```

## 🛡️ Portfolio Risk (`domain::portfolio_risk`)

```rust
use quant-engine::domain::portfolio_risk::{
    portfolio::{
        PortfolioOptimizer, HRP, MV, RiskParity, BlackLitterman,
    },
    risk::{
        RiskModel, CovarianceEstimator, ShrunkCovariance,
        FactorRiskModel, HistoricalCovariance,
    },
    measures::{
        RiskMeasures, VaR, CVaR, MaxDrawdown, UlcerIndex,
        PainIndex, Sterling, Calmar,
    },
    stress_testing::StressTester,
    margin::MarginCalculator,
    transaction_aware::TransactionAwareOptimization,
    nco::NCO,
    online_portfolio::OnlinePortfolio,
    insurance::PortfolioInsurance,
};
```

### Portfolio Optimization Pipeline
1. `ShrunkCovariance::estimate(returns, alpha=0.3)` → matriz shrinkeada
2. `FactorRiskModel::decompose(cov, factor_loadings)` → riesgo sistemático
3. `NCO::new(factors, assets).cluster().optimize()` → NCO weights
4. `RiskParity::optimize(cov, max_leverage=2.0)` → risk parity weights
5. `BlackLitterman::with_views(prior, views, confidence)` → BL weights

> Risk Limits (hard stops VaR/CVaR en el hot path) permanece en `SKILL.md`:
> es esencia accionable, no detalle de API.
