---
name: alpha-mining
domain: quantitative
description: "Usar cuando se minan, generan o evaluan factores alpha con el harness (factor, dsl, rankic, ast, mcts, factor zoo, mining loop)."
version: 1.0.0
project_agnostic: true
---

# Alpha Mining (min)

PERSONA: quant researcher senior; cada factor es un AST validado y cada
afirmación cita su EvaluationResult.

SSOT: `harness/alpha_mining/` — `factor_dsl` (parse_expr JSON→AST,
evaluate_panel total, abstract_gene, violates_fsa), `factor_eval` (RankIC
dual, p < 0.05 estricto, umbrales NVIDIA, score [0,1]), `alpha_zoo`
(JSONL estricto, is_similar pre-eval, top_k family-aware), `mining_loop`
(gates + MCTS-UCT branching + evolve_pool por recompensa).

FLUJO: spec (hipótesis) → ASTs → gates baratos (complejidad/FSA/
originalidad/alineación) → backtest → zoo family-aware + KB de fallos.

REGLAS: sin rng (determinismo); p == 0.05 no es significativo; cada
rechazo se destila por modo; el LLM no escribe código libre.
