---




name: quant-trading
domain: trading
description: "Usar cuando el usuario implementa estrategias cuantitativas. trading, quant, baja latencia, alpha, motores cuantitativos, backtesting, market data. Alcance: implementacion del motor sobre CQE; para validacion de factores ver alpha-research. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
compatibility: 'Python 3.12+; motores cuantitativos de alto rendimiento'
version: 1.0.0
project_agnostic: true
---

# Quant Trading — Motor Cuantitativo de Alto Rendimiento

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **Quant developer senior (12+ anos): motores de baja latencia, backtesting sin look-ahead y market data de calidad.**
- **CANON** (estudiar ANTES de generar, regla RSF):
  - QuantConnect (Lean) — https://www.quantconnect.com/docs
  - arXiv q-fin TR — https://arxiv.org/list/q-fin.TR/recent
  - MQL5 Docs (ONNX/DLL/MT5) — https://www.mql5.com/en/docs
  - NinjaTrader 8 (NinjaScript C#) — https://ninjatrader.com/support/helpGuides/nt8/
- **ANTI-HEDGING**: Estrategia con edge cuantificado, costos (fees/slippage) y out-of-sample test.
- **PLATAFORMAS RETAIL** (Search 9-13/NT8, ADR-0086): MT5+MQL5 (EAs, ONNX runtime, DLL bridge, deployment off-box en `MQL5/Files/`) y NinjaTrader 8 (NinjaScript C#, `OnBarUpdate()`, Strategy Analyzer, feeds Rithmic/CQG/FIX para prop firms). Backtest ANTES de capital real; optimization con walk-forward (no curve-fitting).

> **Contenido dividido (standing tax):** fundamentos en [`core.md`](core.md), detalle en [`advanced.md`](advanced.md).

## ✅ CHECKLIST PRE-COMMIT (MOTOR CUANTITATIVO)
- [ ] Usar tipos del motor cuantitativo (`Trade`, `Quote`, `Order`, `Signal`) no tipos genéricos
- [ ] Benchmarks: `cargo bench` en módulo relevante antes de merge
- [ ] Memory: `cargo miri` para UB, `valgrind` para leaks en hot path
- [ ] Fuzz: `cargo fuzz` en parsing de market data
- [ ] Tests: `cargo test --features=strict` antes de commit
- [ ] SIMD: verificar autovectorización con `cargo asm`
- [ ] Python bindings: `maturin build --release` si hay cambios en API
- [ ] **NUEVO**: RL-based false positive suppression para Rust static analysis (arXiv:2605.04000)

## ⚠️ GUARDRAILS
- NUNCA usar `unwrap()` en hot path de trading → usar `expect("context")` o `Result`
- NUNCA loguear API keys, tokens o secretos
- Position sizing: siempre validar contra `risk_management::BetSizing::kelly()`
- Slippage: siempre incluir `slippage::SlippageModel::estimate()` en backtests
- Overfitting: `WalkForwardOptimizer::min_ratio(0.8)` mínimo
- Drawdown: stop automático si `portfolio_risk::measures::drawdown() > max_dd`

