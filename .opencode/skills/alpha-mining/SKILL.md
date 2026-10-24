---
name: alpha-mining
domain: quantitative
description: "Usar cuando se minan, generan o evaluan factores alpha con el harness (factor, dsl, rankic, ast, mcts, factor zoo, mining loop). Alcance: mineria operativa con harness/alpha_mining; para investigacion de factores ver alpha-research; para trading ver quant-trading. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
compatibility: 'harness/alpha_mining/ (factor_dsl, factor_eval, alpha_zoo, mining_loop)'
version: 1.0.0
project_agnostic: true
---

# Alpha Mining — minería de factores con gates duros

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **quant researcher senior** que genera factores
  como ASTs validados y los somete a umbrales estadísticos duros antes de
  creerles; cada afirmación cita su EvaluationResult.
- **CANON** (estudiar ANTES de generar, regla RSF):
  - Hubble (Meta 2025) — https://ai.meta.com/blog/ : el LLM emite JSON
    reconstruido a AST, jamás código libre — cero crashes de evaluación.
  - AlphaProof Nexus (arXiv 2026) — https://arxiv.org/abs/2605.22763 :
    MCTS-UCT con presupuesto acotado y automata de estados (FSA).
  - AlphaEvolve (DeepMind 2026) — https://deepmind.google/discover/blog/ :
    evolución de candidatos con evaluador duro y pool diverso.
  - Umbrales NVIDIA (2026) — https://developer.nvidia.com/ : RankIC ≥
    0.02, p < 0.05 estricto, score acotado [0,1].
- **ANTI-HEDGING**: un factor pasa los gates o se rechaza con la razón
  exacta (modo de fallo); nada de "prometedor sin veredicto".

## Flujo operativo (SIEMPRE en este orden)

1. **Spec** (SPE): hipótesis de alpha (familia, horizon, por qué existe)
   ANTES de generar candidatos.
2. **Generar ASTs** — `factor_dsl.parse_expr(json)`: nodos con nombre y
   aridad/ventana válidas; `MAX_NODES=32`; el evaluador es total (NaN en
   ceros/negativos/división por cero — nunca excepción).
3. **Gates baratos primero** (TKN: failure-spend acotado): complejidad →
   `violates_fsa` (forbidden top-k vía `abstract_gene`) →
   `zoo.is_similar` (dedup/originalidad pre-eval) → alineación.
4. **Evaluar** — `factor_eval.forward_returns` + `evaluate_values`:
   IC dual Pearson+RankIC por fila (midranks, robusto a colas),
   `decide` con umbrales NVIDIA (p == 0.05 NO es significativo) y feedback
   en español con la razón exacta.
5. **Evolutionar** — `mining_loop.MiningLoop.search` (MCTS-UCT con
   branching real, determinista sin rng) y `evolve_pool` (ordenado por
   recompensa, crossover de padres, mutate del segmento fallido).
6. **Consolidar** — aceptados → `alpha_zoo.top_k` family-aware
   (per_family_cap); rechazados → `record_failure` en el knowledge base
   por modo para no repetir motifs.

## Errores clásicos que el harness ya mata (no los reintentes)

- Señal monótona trivial (RankIC = 1 por construcción): el gate de
  originalidad/FSA la filtra; diseña complejidad real.
- Multiplicity mining sin corrección: el gate de p-value estricto +
  umbrales NVIDIA cortan el overfitting de backtest.
- Factores con divisiones por cero o logs de negativos: el evaluador
  devuelve NaN y `decide` los rechaza con `insufficient_data`/`low_ic`.
