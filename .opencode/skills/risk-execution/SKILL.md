---



name: risk-execution
domain: trading
description: "Usar cuando el usuario gestiona riesgo o ejecucion algoritmica. position sizing, market making, TCA, riesgo institucional, ejecucion algoritmica. Alcance: implementacion tactica; para doctrina institucional ver hedgefund. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
compatibility: 'Python 3.12+'
version: 1.0.0
project_agnostic: true
---

# Risk & Execution — Gestión de Riesgo Institucional

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **Execution trader senior (12+ anos): position sizing, market making, TCA y riesgo institucional en vivo.**
- **CANON** (estudiar ANTES de generar, regla RSF):
  - CFA Institute (risk) — https://www.cfainstitute.org
  - ARPM — https://www.arpm.co
- **ANTI-HEDGING**: Sizing explicito con drawdown maximo y razon de Kelly limitada; sin 'a ojo'.

## Position Sizing por estrategia (ESENCIAL)
| Estrategia | Método | CQE | Fracción |
|-----------|--------|-----|----------|
| Trend following | Half-Kelly | `HalfKelly::compute(edge, odds)` | 12.5% |
| Mean reversion | Quarter-Kelly | `QuarterKelly::compute(edge, odds)` | 6.25% |
| HFT/Market making | VolParity | `VolatilityParity::weight()` | 2-5% |
| ML signals | Confidence-Weighted | `ConfidenceWeighted::size(pred_prob)` | Variable |
| Diversified portfolio | Full-Kelly corregido | `KellyCriterion::multi_asset(cov_matrix)` | 16.6% |

## Execution algorithms (ESENCIAL)
| Algoritmo | Uso | CQE Module | Implementation shortfall |
|-----------|-----|-----------|------------------------|
| TWAP | Grandes órdenes, baja urgencia | `TWAP::execute(quantity, horizon)` | 0.05-0.15% |
| VWAP | Benchmark contra volumen | `VWAP::execute(quantity, target_volume)` | 0.08-0.20% |
| Implementation Shortfall | Alta urgencia | `ImplementationShortfall::execute(urgency=0.8)` | 0.15-0.40% |
| Adaptive Algo | ML-driven | `AdaptiveAlgo::execute(ml_signal, lob)` | 0.03-0.12% |

## Risk Limits (HARD — se ejecutan en Rust hot path)
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
- `portfolio_risk::insurance::PortfolioInsurance` siempre activo (tail hedge)
- `risk_guards::circuit_breaker(portfolio_dd > 0.20)` → liquidación automática
- `compliance::RiskControls::validate(order, portfolio)` → pre-trade check
- `margin::MarginCalculator::maintenance()` → monitoreo en tiempo real
- **NUEVO**: Mean Field Control para crowding risk en mercados concentrados
- **NUEVO**: PIKAN para portfolio optimization con regularizacion fisica

## Anti-patrones (prohibidos)

- Sizing 'a ojo' sin drawdown maximo ni Kelly limitada.
- Ignorar costes de transaccion en TCA.
- Market making sin inventario maximo.
- Asumir liquidez sin modelar impacto.
- Exceder el limite institucional sin aprobacion.

## Referencias (bajo demanda)

> Migrado a `references/` por política "focused beats comprehensive" (SkillsBench 2026).
> Cargar solo cuando la tarea requiera el detalle de APIs o la frontera.

- [Modelos de riesgo (APIs CQE)](references/modelos-riesgo.md) — módulos Rust `risk_management`/`portfolio_risk`, EVT, pipeline de optimización.
- [Ejecución algorítmica y TCA](references/ejecucion-algoritmica.md) — módulo `execution`, market making Avellaneda-Stoikov, análisis de costes.
- [Frontier 2026 — ejecución y riesgo](references/frontier-2026.md) — actor-critic mean-field, PIKAN, tabla 2026.

## Ejemplo

Con capital 100k y riesgo 1 % por trade: position size = (100k x 0.01) / (entry - stop); si el slippage medido supera 10 bps, reduce el tamano a la mitad.
