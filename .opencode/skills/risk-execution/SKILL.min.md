---
name: risk-execution
description: "Usar cuando el usuario gestiona riesgo o ejecucion algoritmica. position sizing, market making, TCA, riesgo institucional, ejecucion algoritmica. Alcance: implementacion tactica; para doctrina institucional ver hedgefund. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
---

# Risk & Execution (min)

## Position Sizing por estrategia
| Estrategia | Método | CQE | Fracción |
|-----------|--------|-----|----------|
| Trend following | Half-Kelly | `HalfKelly::compute(edge, odds)` | 12.5% |
| Mean reversion | Quarter-Kelly | `QuarterKelly::compute(edge, odds)` | 6.25% |
| HFT/Market making | VolParity | `VolatilityParity::weight()` | 2-5% |
| ML signals | Confidence-Weighted | `ConfidenceWeighted::size(pred_prob)` | Variable |
| Diversified portfolio | Full-Kelly corregido | `KellyCriterion::multi_asset(cov_matrix)` | 16.6% |

## Risk Limits (HARD)
- VaR 95% + CVaR 99% (expected shortfall) + max drawdown 252d + ulcer index 14d.
- `if daily_risk.cvar_99 > PORTFOLIO_CVAR_LIMIT` → `risk_guards::reduce_exposure(0.5)`.
- Todo se ejecuta en Rust hot path (sin allocations, sin GC pauses).

## Execution algorithms
| Algoritmo | Uso | CQE Module | Shortfall |
|-----------|-----|-----------|-----------|
| TWAP | baja urgencia | `TWAP::execute(quantity, horizon)` | 0.05-0.15% |
| VWAP | benchmark volumen | `VWAP::execute(quantity, target_volume)` | 0.08-0.20% |
| Impl. Shortfall | alta urgencia | `ImplementationShortfall::execute(urgency=0.8)` | 0.15-0.40% |
| Adaptive Algo | ML-driven | `AdaptiveAlgo::execute(ml_signal, lob)` | 0.03-0.12% |

## ✅ CHECKLIST PRE-COMMIT RIESGO
- [ ] Position sizing validado contra Kelly Criterion
- [ ] VaR/CVaR calculado con EVT (colas pesadas)
- [ ] Stress test: 2008, COVID, flash crash en portfolio
- [ ] Slippage model incluido en todas las simulaciones
- [ ] TCA post-trade para todas las órdenes ejecutadas
- [ ] Drawdown limit hardcoded (no configurable en prod)
- [ ] Circuit breakers: max position, max leverage, max correlation
- [ ] Rust hot path: sin allocations en loop de trading, pre-alloc buffers

## ⚠️ GUARDRAILS HARD
- `PortfolioInsurance` siempre activo (tail hedge).
- `circuit_breaker(portfolio_dd > 0.20)` → liquidación automática.
- `RiskControls::validate(order, portfolio)` → pre-trade check.
- `MarginCalculator::maintenance()` → monitoreo en tiempo real.
- Frontier: Mean Field Control (crowding) + PIKAN.

## Anti-patrones
- Sizing 'a ojo' sin drawdown maximo ni Kelly limitada.
- Ignorar costes de transaccion en TCA.
- Market making sin inventario maximo.
- Asumir liquidez sin modelar impacto.
- Exceder el limite institucional sin aprobacion.

## Referencias (bajo demanda)
- [Modelos de riesgo](references/modelos-riesgo.md)
- [Ejecución algorítmica y TCA](references/ejecucion-algoritmica.md)
- [Frontier 2026](references/frontier-2026.md)
