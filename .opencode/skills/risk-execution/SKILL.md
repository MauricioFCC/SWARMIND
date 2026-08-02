---


name: risk-execution
domain: trading
description: "Gestión de riesgo institucional y ejecución algorítmica con motores cuantitativos de alto rendimiento (ej. CQE Rust) — position sizing, market making, TCA. UPG: usar ultima version estable (pyproject.toml/uv.lock al dia). NAM: snake_case archivos+vars+funcs, PascalCase clases, UPPER_SNAKE constants, sin magic numbers, nombres comprensibles"
---

# Risk & Execution — Gestión de Riesgo Institucional

Gestión de riesgo y ejecución algorítmica de nivel institucional, implementable sobre motores cuantitativos (ej. CQE Rust).
Prioriza: preservación de capital > Sharpe > alpha bruto.

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

### Position Sizing por estrategia
| Estrategia | Método | CQE | Fracción |
|-----------|--------|-----|----------|
| Trend following | Half-Kelly | `HalfKelly::compute(edge, odds)` | 12.5% |
| Mean reversion | Quarter-Kelly | `QuarterKelly::compute(edge, odds)` | 6.25% |
| HFT/Market making | VolParity | `VolatilityParity::weight()` | 2-5% |
| ML signals | Confidence-Weighted | `ConfidenceWeighted::size(pred_prob)` | Variable |
| Diversified portfolio | Full-Kelly corregido | `KellyCriterion::multi_asset(cov_matrix)` | 16.6% |

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

### Risk Limits
```rust
let daily_risk = RiskMeasures::compute(&portfolio_returns)
    .var_95(0.95)           // VaR 95% diario
    .cvar_99(0.99)          // CVaR 99% (expected shortfall)
    .max_drawdown(252)       // Max drawdown 1 año
    .ulcer_index(14);        // Ulcer index 14 días

// Hard stops (se ejecutan en Rust hot path, sin GC pauses)
if daily_risk.cvar_99 > PORTFOLIO_CVAR_LIMIT {
    risk_guards::reduce_exposure(0.5);  // reducir 50%
}
```

## ⚡ Execution (`domain::execution`)

```rust
use quant-engine::domain::execution::{
    execution::{
        ExecutionEngine, ExecutionAlgorithm, TWAP, VWAP, 
        POV, ImplementationShortfall, AdaptiveAlgo,
    },
    impact::{
        MarketImpact, AlmgrenChriss, Kissell, 
        SquareRootImpact,
    },
    lob::{
        OrderBook, LOBImbalance, LiquidityScore,
    },
    market_making::{
        MarketMaker, AvellanedaStoikov, OptimalSpread,
        InventoryManager, SkewModel,
    },
    matching_engine::MatchingEngine,
    tca::{
        TransactionCostAnalysis, TCAReport, CostBreakdown,
    },
};
```

### Execution algorithms
| Algoritmo | Uso | CQE Module | Implementation shortfall |
|-----------|-----|-----------|------------------------|
| TWAP | Grandes órdenes, baja urgencia | `TWAP::execute(quantity, horizon)` | 0.05-0.15% |
| VWAP | Benchmark contra volumen | `VWAP::execute(quantity, target_volume)` | 0.08-0.20% |
| Implementation Shortfall | Alta urgencia | `ImplementationShortfall::execute(urgency=0.8)` | 0.15-0.40% |
| Adaptive Algo | ML-driven | `AdaptiveAlgo::execute(ml_signal, lob)` | 0.03-0.12% |

### Market Making (Avellaneda-Stoikov)
```rust
let mm = MarketMaker::new()
    .model(InventoryModel::AvellanedaStoikov)
    .risk_aversion(0.1)          // gamma: aversión al riesgo
    .position_limit(100)          // max inventory
    .spread_model(SpreadModel::Dynamic)
    .reservation_price(mid_price, inventory, gamma, sigma, T)
    .optimal_spread(gamma, sigma, T, kappa);
// bid = reservation_price - spread/2
// ask = reservation_price + spread/2
```

## 🔬 TCA (Transaction Cost Analysis)

```rust
let tca = TransactionCostAnalysis::new(trades, benchmark=VWAP)
    .analyze()
    .breakdown(|cost| CostBreakdown {
        spread_cost: cost.spread,
        market_impact: cost.impact,
        timing_risk: cost.timing,
        opportunity_cost: cost.opportunity,
        total: cost.total,
    });
```

## ✅ CHECKLIST PRE-COMMIT RIESGO
- [ ] Position sizing validado contra Kelly Criterion
- [ ] VaR/CVaR calculado con EVT (colas pesadas)
- [ ] Stress test: 2008, COVID, flash crash en portfolio
- [ ] Slippage model incluido en todas las simulaciones
- [ ] TCA post-trade para todas las órdenes ejecutadas
- [ ] Drawdown limit hardcoded (no configurable en prod)
- [ ] Circuit breakers: max position, max leverage, max correlation
- [ ] Rust hot path: sin allocations en loop de trading, pre-alloc buffers

## 🆕 Frontier 2026 — Ejecucion y Riesgo

### Actor-Critic para Liquidacion Optima con Crowding
```rust
use execution::mean_field::ExtendedMeanFieldControl;

// Model-free RL para ejecucion considerando crowding de trades
let liquidacion = ExtendedMeanFieldControl::new()
    .dynamics("mckean_vlasov")     // Dinamica que depende de la distribucion conjunta
    .policy("deterministic_feedback")  // Politica determinista (evita kernels estocasticos)
    .rl_algorithm("continuous_td3")   // Deep Deterministic Policy Gradient en tiempo continuo
    .crowding_penalty(0.3)            // Penalizacion por impacto agregado
    .solve(horizon=60, steps=1000);   // Horizonte 60min, 1000 pasos
// Reference: arXiv:2607.11005 — Actor-Critic for Mean Field Control (Jul 2026)
// Resultado: Estable y robusto con trade crowding, supera TWAP/VWAP en mercados concentrados
```

### PIKAN para Portfolio Risk
```rust
// KANs con regularizacion fisica para optimizacion de portfolio
use pikan::PIKANPortfolio;

let risk_portfolio = PIKANPortfolio::new()
    .kan_layers(&[128, 64, 32])
    .risk_measure("expected_shortfall_975")
    .physics_regularization(0.15)
    .constraints(max_leverage=2.0, max_holding=0.1);
// Sharpe +25-40%, Calmar +30-50%, drawdown -40% vs DRL clasico
// Reference: arXiv:2602.01388 (Feb 2026)
```

### Actualizacion — Execution Algorithms 2026
| Algoritmo | Uso | CQE Module | Implementation shortfall | Paper |
|-----------|-----|-----------|------------------------|-------|
| TWAP | Grandes órdenes, baja urgencia | `TWAP::execute(quantity, horizon)` | 0.05-0.15% | Clásico |
| VWAP | Benchmark contra volumen | `VWAP::execute(quantity, target_volume)` | 0.08-0.20% | Clásico |
| Implementation Shortfall | Alta urgencia | `ImplementationShortfall::execute(urgency=0.8)` | 0.15-0.40% | Almgren-Chriss |
| Adaptive Algo | ML-driven | `AdaptiveAlgo::execute(ml_signal, lob)` | 0.03-0.12% | CQE v2.1 |
| **Extended MFC** | **Liquidacion con crowding** | **`MeanFieldControl::solve()`** | **0.02-0.08%** | **arXiv:2607.11005** |

## ⚠️ GUARDRAILS HARD
- `portfolio_risk::insurance::PortfolioInsurance` siempre activo (tail hedge)
- `risk_guards::circuit_breaker(portfolio_dd > 0.20)` → liquidación automática
- `compliance::RiskControls::validate(order, portfolio)` → pre-trade check
- `margin::MarginCalculator::maintenance()` → monitoreo en tiempo real
- **NUEVO**: Mean Field Control para crowding risk en mercados concentrados
- **NUEVO**: PIKAN para portfolio optimization con regularizacion fisica

