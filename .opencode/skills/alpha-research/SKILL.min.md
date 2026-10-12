---
name: alpha-research
description: "Usar cuando el usuario busca investigar o validar factores de alpha. alpha, factores, ML, feature engineering, validacion estadistica, backtesting. Alcance: investigacion (falsacion, walk-forward); para motor de datos ver quant-trading. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
---

# Alpha Research (min)

## Anti-overfitting system (falsación primero) 🛡️
1. `TripleBarrierLabeling::label(returns, barrier=2.0, time=20)` → labeling
2. `CrossValidator::purged_walk_forward(n_folds=5, purge=50)` → CV purgado
3. `BootstrapTest::sharpe_ratio(metric, n_iterations=10000)` → p-value del Sharpe
4. `DatasetShiftDetector::detect(in_sample, out_sample)` → data snooping
5. `DeflatedSR::probability(expected_n=200)` → SR ajustado por múltiples tests

### Umbrales (HARD)
- DSR > 0.95 → alpha real. DSR < 0.5 → probable sobreajuste.
- Out-of-sample mínimo 30% del periodo total.
- Walk-forward 5 folds purgados; bootstrap 10,000 muestras.

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

## Anti-patrones
- Data snooping / overfitting a un unico backtest.
- Look-ahead bias o survivorship bias en features.
- Reportar Sharpe sin costes, slippage ni capacidad.
- Multiples pruebas sin correccion (FDR/Bonferroni) -> falsos positivos.
- Confundir correlacion con causalidad.

## Referencias (bajo demanda)
- [Factor Zoo y ML avanzado](references/factor-zoo-y-ml.md)
- [Validación y construcción de portafolio](references/validacion-y-portafolio.md)
- [Frontier 2026](references/frontier-2026.md)
