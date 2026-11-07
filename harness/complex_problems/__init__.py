"""Mecanismos de resolucion de problemas complejos (ciclo 11.17 — Nexus).

Paquete que destila los mecanismos de los sistemas que resolvieron
problemas del milenio (AlphaProof, AlphaEvolve, AlphaProof Nexus 9/353
de Erdos): escalera de presupuesto, verificador formal inyectado con
anti-malformalizacion, poblacion de sketches con Elo, P-UCB sobre
familias y ledger monotono persistente — orquestados por ``AttackLoop``.
"""

from __future__ import annotations

from harness.complex_problems.attack import AttackLoop, AttackReport, AttemptRecord
from harness.complex_problems.budget import (
    DEFAULT_EPISODE_CAP,
    AttackBudget,
    BudgetLadder,
)
from harness.complex_problems.p_ucb import DEFAULT_EXPLORATION, PopulationUCB
from harness.complex_problems.progress import ProgressLedger
from harness.complex_problems.sketch_store import (
    DEFAULT_INITIAL_RATING,
    DEFAULT_K_FACTOR,
    Sketch,
    SketchStore,
)
from harness.complex_problems.verifier import (
    VerificationResult,
    Verifier,
    check_statement_integrity,
)

__all__ = [
    "DEFAULT_EPISODE_CAP",
    "DEFAULT_EXPLORATION",
    "DEFAULT_INITIAL_RATING",
    "DEFAULT_K_FACTOR",
    "AttackBudget",
    "AttackLoop",
    "AttackReport",
    "AttemptRecord",
    "BudgetLadder",
    "PopulationUCB",
    "ProgressLedger",
    "Sketch",
    "SketchStore",
    "VerificationResult",
    "Verifier",
    "check_statement_integrity",
]
