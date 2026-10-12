# Ejecución Algorítmica y TCA — detalle bajo demanda

> Migrado de `SKILL.md` a `references/` por política "focused beats comprehensive"
> (SkillsBench 2026, arXiv:2602.12670). La tabla de algoritmos permanece en
> `SKILL.md` como esencia; aquí vive el detalle de módulos, market making y TCA.

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
