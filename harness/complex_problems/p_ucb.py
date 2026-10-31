"""P-UCB sobre familias de sketches (ciclo 11.17 — AlphaProof Nexus).

WHAT: Upper Confidence Bound determinista sobre familias de sketches con
fitness binario (AlphaProof Nexus, arXiv 2605.22763): cobertura garantizada
(cada familia se prueba al menos una vez antes de repetir) y luego
explotacion de la tasa de exito con bonus de exploracion; empates -> la
primera familia en orden de declaracion (sin rng).

WHY: sin cobertura, la busqueda se congela en la primera familia con un
acierto temprano (sesgo de arranque); con UCB puro, la exploracion queda
balanceada contra la explotacion sin hiperparametro de epsilon.

WHERE: ``harness/complex_problems/p_ucb.py``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType

#: Constante de exploracion por defecto (sqrt(2) del linaje AlphaZero).
DEFAULT_EXPLORATION = math.sqrt(2.0)


class PopulationUCB:
    """Seleccion UCB entre familias de sketches (fitness binario)."""

    def __init__(
        self,
        arms: Sequence[str],
        *,
        exploration: float = DEFAULT_EXPLORATION,
    ) -> None:
        if not arms:
            raise ValueError(
                "WHAT: familias vacias. WHY: UCB requiere al menos un brazo. "
                "WHERE: PopulationUCB."
            )
        if len(set(arms)) != len(arms):
            raise ValueError(
                f"WHAT: familia duplicada en {tuple(arms)}. WHY: los brazos "
                "son un conjunto. WHERE: PopulationUCB."
            )
        if exploration <= 0:
            raise ValueError(
                f"WHAT: exploracion {exploration} no positiva. WHY: sin bonus "
                "no hay cobertura. WHERE: PopulationUCB."
            )
        self._arms = tuple(arms)
        self._exploration = exploration
        self._pulls: dict[str, int] = {arm: 0 for arm in arms}
        self._wins: dict[str, int] = {arm: 0 for arm in arms}

    @property
    def pulls(self) -> Mapping[str, int]:
        """Tiradas por familia (vista inmutable)."""
        return MappingProxyType(self._pulls)

    @property
    def wins(self) -> Mapping[str, int]:
        """Victorias por familia (vista inmutable)."""
        return MappingProxyType(self._wins)

    @property
    def total_pulls(self) -> int:
        """Total de tiradas registradas."""
        return sum(self._pulls.values())

    @property
    def exploration(self) -> float:
        """Constante de exploracion del bonus UCB."""
        return self._exploration

    def select(self) -> str:
        """Familia a probar: cobertura primero, despues UCB (empate -> orden)."""
        for arm in self._arms:
            if self._pulls[arm] == 0:
                return arm
        log_total = math.log(self.total_pulls)
        best_arm = self._arms[0]
        best_score = self._score(best_arm, log_total)
        for arm in self._arms[1:]:
            score = self._score(arm, log_total)
            if score > best_score:
                best_arm, best_score = arm, score
        return best_arm

    def record(self, arm: str, won: bool) -> None:
        """Registra el resultado binario de una tirada de ``arm``.

        Raises:
            KeyError: Si la familia no pertenece a la poblacion.
        """
        if arm not in self._pulls:
            raise KeyError(
                f"WHAT: familia '{arm}' desconocida. WHY: solo brazos del "
                "store. WHERE: PopulationUCB.record."
            )
        self._pulls[arm] += 1
        if won:
            self._wins[arm] += 1

    def _score(self, arm: str, log_total: float) -> float:
        pulls = self._pulls[arm]
        exploit = self._wins[arm] / pulls
        explore = self._exploration * math.sqrt(log_total / pulls)
        return exploit + explore
