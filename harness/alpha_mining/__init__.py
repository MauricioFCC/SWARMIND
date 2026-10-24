"""Alpha mining: mineria de factores con la frontera 2026 (ciclo 11.16).

Paquete que implementa las capacidades de los 5 sistemas frontera de
mineria alpha (QuantaAlpha, AlphaAgent, Hubble, AlphaMCTS y el pipeline
signal/code/eval de NVIDIA) sobre un nucleo determinista y verificable:

- ``factor_dsl``: AST tipado + evaluador total + gates estructurales.
- ``factor_eval``: IC/RankIC dual + significancia + decision del eval agent.
- ``alpha_zoo``: zoo durable + KB de fallos + seleccion family-aware.
- ``mining_loop``: bucle cerrado + MCTS-UCT + evolucion de trayectorias.

Los LLMs se inyectan como hooks (DI): el nucleo es 100% testeable sin red.
"""

from __future__ import annotations

from harness.alpha_mining.alpha_zoo import (
    AlphaZoo,
    FactorFamily,
    ZooEntry,
    classify_family,
)
from harness.alpha_mining.factor_dsl import (
    MAX_NODES,
    Expr,
    Field,
    Operator,
    abstract_gene,
    complexity,
    evaluate,
    forbidden_genes,
    parse_expr,
    subtree_similarity,
    to_dict,
    to_formula,
    validate_expr,
    violates_fsa,
)
from harness.alpha_mining.factor_eval import (
    DEFAULT_MIN_ABS_IC,
    DEFAULT_P_VALUE_MAX,
    EvalVerdict,
    FactorMetrics,
    decide,
    evaluate_factor,
    evaluate_values,
    forward_returns,
)
from harness.alpha_mining.mining_loop import (
    ALIGNMENT_MIN,
    LoopConfig,
    MCTSResult,
    MiningContext,
    MiningLoop,
    Role,
    RoundReport,
    Trajectory,
    TrajectoryStep,
    crossover,
    mutate,
)

__all__ = [
    "ALIGNMENT_MIN",
    "DEFAULT_MIN_ABS_IC",
    "DEFAULT_P_VALUE_MAX",
    "MAX_NODES",
    "AlphaZoo",
    "EvalVerdict",
    "Expr",
    "FactorFamily",
    "FactorMetrics",
    "Field",
    "LoopConfig",
    "MCTSResult",
    "MiningContext",
    "MiningLoop",
    "Operator",
    "Role",
    "RoundReport",
    "Trajectory",
    "TrajectoryStep",
    "ZooEntry",
    "abstract_gene",
    "classify_family",
    "complexity",
    "crossover",
    "decide",
    "evaluate",
    "evaluate_factor",
    "evaluate_values",
    "forbidden_genes",
    "forward_returns",
    "mutate",
    "parse_expr",
    "subtree_similarity",
    "to_dict",
    "to_formula",
    "validate_expr",
    "violates_fsa",
]
