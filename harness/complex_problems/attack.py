"""Loop de ataque a problemas complejos (ciclo 11.17 — AlphaProof Nexus).

WHAT: orquestador integrador de los 5 mecanismos del sistema Nexus
(arXiv 2605.22763): escalera de presupuesto + verificador formal inyectado
+ anti-malformalizacion + ledger monotono (+ poblacion Elo disponible por
DI para guiar el candidate_hook). Cada intento reserva presupuesto, genera
un candidato via hook, verifica integridad del statement y certificacion
formal; si verifica, el problema queda resuelto para siempre (idempotente).

WHY: los mecanismos aislados no dan el sistema; el loop es el contrato
integrador — determinista (sin rng), DI completa (verifier/hook/ledger
inyectados) y con failure-spend acotado (cap global de episodios).

WHERE: ``harness/complex_problems/attack.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from harness.complex_problems.budget import (
    DEFAULT_EPISODE_CAP,
    AttackBudget,
    BudgetLadder,
)
from harness.complex_problems.progress import ProgressLedger
from harness.complex_problems.verifier import Verifier, check_statement_integrity


@dataclass(frozen=True)
class AttemptRecord:
    """Intento del loop: grant, gasto y si el candidato verifico."""

    attempt: int
    granted: int
    spent: int
    verified: bool


@dataclass(frozen=True)
class AttackReport:
    """Reporte inmutable del ataque a un problema."""

    problem_id: str
    solved: bool
    attempts: int
    spent: int
    evidence: str | None
    history: tuple[AttemptRecord, ...] = field(default_factory=tuple)


class AttackLoop:
    """Loop determinista presupuesto x verificacion x monotonía (Nexus)."""

    def __init__(
        self,
        *,
        verifier: Verifier,
        ledger: ProgressLedger,
        candidate_hook: Callable[[int, str], str],
        ladder: BudgetLadder,
        cost_per_attempt: int = 1,
        episode_cap: int = DEFAULT_EPISODE_CAP,
    ) -> None:
        if cost_per_attempt <= 0:
            raise ValueError(
                f"WHAT: cost_per_attempt {cost_per_attempt} no positivo. "
                "WHY: cada intento consume al menos un episodio. "
                "WHERE: AttackLoop."
            )
        self._verifier = verifier
        self._ledger = ledger
        self._hook = candidate_hook
        self._ladder = ladder
        self._cost = cost_per_attempt
        self._cap = episode_cap

    def attack(
        self,
        problem_id: str,
        statement: str,
        *,
        required_markers: Sequence[str] = (),
        max_attempts: int = 3,
    ) -> AttackReport:
        """Ataca ``problem_id`` hasta resolverlo, agotar presupuesto o rendirse.

        Args:
            problem_id: Identificador estable del problema.
            statement: Enunciado formal (para el gate anti-malformalizacion).
            required_markers: Marcadores que el statement real debe contener.
            max_attempts: Intentos maximos (>= 1).

        Returns:
            AttackReport con historial de intentos y evidencia si resolvio.
        """
        if not problem_id:
            raise ValueError(
                "WHAT: problem_id vacio. WHY: la identidad del problema es "
                "el eje del ledger. WHERE: AttackLoop.attack."
            )
        if max_attempts < 1:
            raise ValueError(
                f"WHAT: max_attempts {max_attempts} < 1. WHY: un ataque "
                "requiere al menos un intento. WHERE: AttackLoop.attack."
            )
        if self._ledger.is_solved(problem_id):
            return AttackReport(
                problem_id=problem_id,
                solved=True,
                attempts=0,
                spent=0,
                evidence=self._ledger.evidence(problem_id),
                history=(),
            )
        missing = check_statement_integrity(statement, required_markers)
        budget = AttackBudget(self._ladder, episode_cap=self._cap)
        history: list[AttemptRecord] = []
        for attempt in range(max_attempts):
            granted = budget.start_attempt(attempt)
            if granted <= 0:
                break
            candidate = self._hook(attempt, problem_id)
            result = self._verifier.verify(candidate)
            verified = (not missing) and result.verified
            spent_now = min(self._cost, granted)
            budget.consume(spent_now)
            history.append(
                AttemptRecord(
                    attempt=attempt,
                    granted=granted,
                    spent=spent_now,
                    verified=verified,
                )
            )
            if verified:
                self._ledger.mark_solved(problem_id, candidate)
                return AttackReport(
                    problem_id=problem_id,
                    solved=True,
                    attempts=len(history),
                    spent=budget.spent_total,
                    evidence=candidate,
                    history=tuple(history),
                )
        return AttackReport(
            problem_id=problem_id,
            solved=False,
            attempts=len(history),
            spent=budget.spent_total,
            evidence=None,
            history=tuple(history),
        )
