"""Escalera de presupuesto de ataque (ciclo 11.17 — AlphaProof Nexus).

WHAT: escalera de presupuesto para ataques a problemas complejos — cada
intento recibe mas compute que el anterior (los intentos tardios atacan con
la direccion ya afinada) y un tope GLOBAL de episodios (cap 3000 del paper
Nexus, arXiv 2605.22763) evita el failure-spend infinito.

WHY: sin escalera, el ataque gasta igual en intentos exploratorios y
prometedores; sin cap global, un hook/perdedor eterno consume compute
ilimitado (Failure-Spend sin registro).

WHERE: ``harness/complex_problems/budget.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Tope GLOBAL de episodios por problema (Nexus: cap 3000 episodios).
DEFAULT_EPISODE_CAP = 3000


@dataclass(frozen=True)
class BudgetLadder:
    """Escalera monotonamente creciente de presupuestos por intento."""

    rungs: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.rungs:
            raise ValueError(
                "WHAT: escalera de presupuesto vacia. WHY: al menos un rung "
                "define el primer intento. WHERE: BudgetLadder."
            )
        for rung in self.rungs:
            if rung <= 0:
                raise ValueError(
                    f"WHAT: rung {rung} no positivo. WHY: cada intento "
                    "consume al menos 1 episodio. WHERE: BudgetLadder."
                )
        for previous, following in zip(self.rungs, self.rungs[1:]):
            if following < previous:
                raise ValueError(
                    f"WHAT: rungs no crecientes ({previous} -> {following}). "
                    "WHY: la escalera da mas compute a los intentos tardios. "
                    "WHERE: BudgetLadder."
                )

    def allocate(self, attempt: int) -> int:
        """Presupuesto del intento ``attempt`` (capado en el ultimo rung)."""
        if attempt < 0:
            raise ValueError(
                f"WHAT: intento negativo {attempt}. WHY: los indices son 0-based. "
                "WHERE: BudgetLadder.allocate."
            )
        return self.rungs[min(attempt, len(self.rungs) - 1)]


class AttackBudget:
    """Gasto acumulado: grants por intento + tope global de episodios.

    Cada ``start_attempt`` reserva (y commitea) el rung correspondiente
    acotado al remanente del cap; ``consume`` gasta episodios dentro de
    ese grant. El presupuesto no usado de un intento se pierde (no se
    acumula entre intentos): la escalera, no el ahorro, decide.
    """

    def __init__(
        self, ladder: BudgetLadder, *, episode_cap: int = DEFAULT_EPISODE_CAP
    ) -> None:
        if episode_cap <= 0:
            raise ValueError(
                f"WHAT: episode_cap {episode_cap} no positivo. WHY: el tope "
                "debe permitir al menos un episodio. WHERE: AttackBudget."
            )
        self._ladder = ladder
        self._cap = episode_cap
        self._committed = 0
        self._attempt_limit = 0
        self._spent_attempt = 0

    @property
    def spent(self) -> int:
        """Episodios gastados en el intento actual."""
        return self._spent_attempt

    @property
    def remaining(self) -> int:
        """Episodios disponibles en el intento actual."""
        return self._attempt_limit - self._spent_attempt

    @property
    def spent_total(self) -> int:
        """Episodios commiteados (reservados) en todos los intentos."""
        return self._committed

    @property
    def exhausted(self) -> bool:
        """True si el cap global se agoto o el grant actual se termino."""
        return self._committed >= self._cap or self.remaining <= 0

    def start_attempt(self, attempt: int) -> int:
        """Reserva el presupuesto del intento y devuelve los episodios otorgados."""
        grant = min(self._ladder.allocate(attempt), self._cap - self._committed)
        self._committed += grant
        self._attempt_limit = grant
        self._spent_attempt = 0
        return grant

    def consume(self, cost: int) -> None:
        """Gasta ``cost`` episodios del grant actual.

        Raises:
            ValueError: Si el costo es negativo o excede el grant restante.
        """
        if cost < 0:
            raise ValueError(
                f"WHAT: costo negativo {cost}. WHY: los episodios solo "
                "crecen. WHERE: AttackBudget.consume."
            )
        if self._committed == 0:
            self.start_attempt(0)
        if cost > self.remaining:
            raise ValueError(
                f"WHAT: costo {cost} sobre el restante {self.remaining}. "
                "WHY: cada intento respeta su grant. WHERE: AttackBudget.consume."
            )
        self._spent_attempt += cost
