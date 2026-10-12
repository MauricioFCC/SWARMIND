# Frontier 2026 — Ejecución y Riesgo — detalle bajo demanda

> Migrado de `SKILL.md` a `references/` por política "focused beats comprehensive"
> (SkillsBench 2026, arXiv:2602.12670). Los guardrails que estos avances refuerzan
> permanecen en `SKILL.md`.

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
