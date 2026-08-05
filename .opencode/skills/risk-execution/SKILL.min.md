---
name: risk-execution
description: "Gestión de riesgo institucional y ejecución algorítmica con motores cuantitativos de alto rendimiento (ej. CQE Rust) — position sizing, market making, TCA | UPG·NAM·FRS (reglas en base_principles.md)"
---

## 📐 Risk Management (`domain::risk_management`)

use quant-engine::domain::risk_management::{
    bet_sizing::{
        KellyCriterion, HalfKelly, QuarterKelly, 

### Position Sizing por estrategia
| Estrategia | Método | CQE | Fracción |
|-----------|--------|-----|----------|
| Trend following | Half-Kelly | `HalfKelly::compute(edge, odds)` | 12.5% |
| Mean reversion | Quarter-Kelly | `QuarterKelly::compute(edge, odds)` | 6.25% |
| HFT/Market making | VolParity | `VolatilityParity::weight()` | 2-5% |
| ML signals | Confidence-Weighted | `ConfidenceWeighted::size(pred_prob)` | Variable |
| Diversified portfolio | Full-Kelly corregido | `KellyCriterion::multi_asset(cov_matrix)` | 16.6% |

### Extreme Value Theory (EVT)
// Modelar colas pesadas para tail risk
let evt = EVTEstimator::new(&returns)
    .method(ExtremeMethod::PeaksOverThreshold)

## 🛡️ Portfolio Risk (`domain::portfolio_risk`)

use quant-engine::domain::portfolio_risk::{
    portfolio::{
        PortfolioOptimizer, HRP, MV, RiskParity, BlackLitterman,

### Portfolio Optimization Pipeline

### Risk Limits
let daily_risk = RiskMeasures::compute(&portfolio_returns)
    .var_95(0.95)           // VaR 95% diario
    .cvar_99(0.99)          // CVaR 99% (expected shortfall)

## ⚡ Execution (`domain::execution`)

use quant-engine::domain::execution::{
    execution::{
        ExecutionEngine, ExecutionAlgorithm, TWAP, VWAP, 

### Execution algorithms
| Algoritmo | Uso | CQE Module | Implementation shortfall |
|-----------|-----|-----------|------------------------|
| TWAP | Grandes órdenes, baja urgencia | `TWAP::execute(quantity, horizon)` | 0.05-0.15% |
| VWAP | Benchmark contra volumen | `VWAP::execute(quantity, target_volume)` | 0.08-0.20% |
| Implementation Shortfall | Alta urgencia | `ImplementationShortfall::execute(urgency=0.8)` | 0.15-0.40% |
| Adaptive Algo | ML-driven | `AdaptiveAlgo::execute(ml_signal, lob)` | 0.03-0.12% |

### Market Making (Avellaneda-Stoikov)
let mm = MarketMaker::new()
    .model(InventoryModel::AvellanedaStoikov)
    .risk_aversion(0.1)          // gamma: aversión al riesgo

## 🔬 TCA (Transaction Cost Analysis)

let tca = TransactionCostAnalysis::new(trades, benchmark=VWAP)
    .analyze()
    .breakdown(|cost| CostBreakdown {

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
use execution::mean_field::ExtendedMeanFieldControl;

// Model-free RL para ejecucion considerando crowding de trades

### PIKAN para Portfolio Risk
// KANs con regularizacion fisica para optimizacion de portfolio
use pikan::PIKANPortfolio;

### Actualizacion — Execution Algorithms 2026
| Algoritmo | Uso | CQE Module | Implementation shortfall | Paper |
|-----------|-----|-----------|------------------------|-------|
| TWAP | Grandes órdenes, baja urgencia | `TWAP::execute(quantity, horizon)` | 0.05-0.15% | Clásico |
| VWAP | Benchmark contra volumen | `VWAP::execute(quantity, target_volume)` | 0.08-0.20% | Clásico |
| Implementation Shortfall | Alta urgencia | `ImplementationShortfall::execute(urgency=0.8)` | 0.15-0.40% | Almgren-Chriss |
| Adaptive Algo | ML-driven | `AdaptiveAlgo::execute(ml_signal, lob)` | 0.03-0.12% | CQE v2.1 |
| **Extended MFC** | **Liquidacion con crowding** | **`MeanFieldControl::solve()`** | **0.02-0.08%** | **arXiv:2607.11005** |

## ⚠️ GUARDRAILS HARD
