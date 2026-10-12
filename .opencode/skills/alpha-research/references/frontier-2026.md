# Frontier 2026 — Alpha Discovery — detalle bajo demanda

> Migrado de `SKILL.md` a `references/` por política "focused beats comprehensive"
> (SkillsBench 2026, arXiv:2602.12670). El checklist de falsación permanece en
> `SKILL.md`; aquí vive la frontera de descubrimiento de factores.

## 🆕 Frontier 2026 — Alpha Discovery

### AlphaCFG — Gramatica Formal para Factores
```rust
use alpha_discovery::AlphaCFG;

// Descubrimiento automatico de factores alfa usando gramatica libre de contexto
let alpha_cfg = AlphaCFG::new()
    .grammar_file("alpha_grammar.cfg")  // Gramatica con restricciones sintacticas
    .search_algorithm("mcts")           // Monte Carlo Tree Search guiado por red
    .value_network(pretrained_model)     // Red de valor sensible a sintaxis
    .policy_network(pretrained_model)    // Red de politica para poda
    .max_depth(6)                       // Profundidad maxima del arbol
    .discover(returns_data, benchmark=500);

// Cada factor generado es:
// - Sintacticamente valido (gramatica)
// - Financieramente interpretable (operadores financieros)
// - Computacionalmente eficiente (O(n) o O(n log n))
// Reference: arXiv:2601.22119 — AlphaCFG (Jan 2026, 24 pages)
// Resultado: Supera SOTA en busqueda de factores en mercados CN + US
```

### PIKAN — Portfolio Optimization con Física
```rust
use pikan::PIKANPortfolio;

// Reemplaza MLPs con Kolmogorov-Arnold Networks en actor y critic
let portfolio = PIKANPortfolio::new()
    .kan_actor(layers=[128, 64, 32], spline_degree=3)
    .kan_critic(layers=[128, 64, 32])
    .physics_loss(weight=0.1)  // 2nd-order temporal consistency
    .rl("SAC");
// Reference: arXiv:2602.01388 — PIKAN (Feb 2026)
// Sharpe +25-40%, Calmar +30-50% vs DRL clasico en CN, VN, US markets
```

### Actualizacion de Modelos — Tabla 2026
| Modelo | Uso | CQE Module | Performance | Paper |
|--------|-----|-----------|-------------|-------|
| AlphaCFG | Factor discovery | `alpha_discovery::AlphaCFG` | Supera SOTA búsqueda factores | arXiv:2601.22119 |
| PIKAN | Portfolio RL | `pikan::PIKANPortfolio` | +25-40% Sharpe vs DRL | arXiv:2602.01388 |
| KAN | Feature interaction | `kan::KolmogorovArnoldNetwork` | +10-15% vs MLP | arXiv:2404.19756 |
| Graph Transformer | Riesgo sistémico | `graph_transformer::GraphTransformer` | +20-30% vs PCA | NeurIPS 2023 |
| Mamba SSM | Long time series | `mamba::MambaSSM` | +15-25% vs LSTM | ICML 2024 |
| Neural CDE | Irregular series | `neural_cde::NeuralCDE` | +12-18% vs RNN | NeurIPS 2022 |
| PCMCI | Causal discovery | `pcmci::PCMCI` | Precursor causal | Science 2019 |
| Conformal | Prediction intervals | `conformal::ConformalPredictor` | Cobertura 95% | JRSS-B 2023 |
