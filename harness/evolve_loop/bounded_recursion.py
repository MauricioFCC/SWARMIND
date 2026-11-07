"""Recursion acotada para el harness (Spec recursive-harness-optimization).

Implementa los limites de profundidad, tokens y tiempo descritos en el spec,
mas early-stopping por convergencia. Envuelve a ``RecursiveHarness`` sin
cambiar su API existente.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

DEFAULT_MAX_DEPTH = int(os.environ.get("HARNESS_MAX_DEPTH", "3"))
DEFAULT_MAX_TOKENS = int(os.environ.get("HARNESS_MAX_TOKENS", "4000"))
DEFAULT_TIMEOUT_SEC = float(os.environ.get("HARNESS_RECURSION_TIMEOUT_SEC", "120"))
EARLY_STOP_PATIENCE = int(os.environ.get("HARNESS_EARLY_STOP_PATIENCE", "2"))


@dataclass
class RecursionBudget:
    """Presupuesto de recursos para una recursion."""

    max_depth: int = DEFAULT_MAX_DEPTH
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout_sec: float = DEFAULT_TIMEOUT_SEC
    tokens_used: int = 0
    depth_used: int = 0
    start_time: float = field(default_factory=time.monotonic)

    def exhausted(self) -> bool:
        """Indica si se agoto algun limite."""
        return (
            self.depth_used >= self.max_depth
            or self.tokens_used >= self.max_tokens
            or time.monotonic() - self.start_time >= self.timeout_sec
        )

    def record(self, tokens: int = 0, depth: int = 1) -> None:
        """Registra consumo de recursos."""
        self.tokens_used += max(0, tokens)
        self.depth_used += max(0, depth)


class BoundedRecursion:
    """Controlador de recursion acotada con early-stopping.

    Envuelve una funcion de recursion (que devuelve un score float) y la
    ejecuta hasta que se agote el presupuesto o converja.

    Uso:
        br = BoundedRecursion(score_fn=my_score, budget=RecursionBudget(max_depth=3))
        best = br.run(initial=0.5)
    """

    def __init__(
        self,
        score_fn: Callable[[int, Any], float],
        budget: RecursionBudget | None = None,
        patience: int = EARLY_STOP_PATIENCE,
    ) -> None:
        """Configura el controlador.

        Args:
            score_fn: Funcion (depth, state) -> score (mayor es mejor).
            budget: Presupuesto de recursos.
            patience: Iteraciones sin mejora antes de early-stop.
        """
        self._score_fn = score_fn
        self._budget = budget or RecursionBudget()
        self._patience = max(1, patience)
        self._history: list[float] = []

    @property
    def budget(self) -> RecursionBudget:
        """Presupuesto activo."""
        return self._budget

    @property
    def history(self) -> list[float]:
        """Historial de scores por iteracion."""
        return list(self._history)

    def run(self, initial: Any = None) -> dict[str, Any]:
        """Ejecuta la recursion acotada.

        Args:
            initial: Estado inicial pasado a score_fn en depth 0.

        Returns:
            Dict con best_score, best_depth, history, stopped_reason.
        """
        best_score = float("-inf")
        best_depth = 0
        no_improve = 0
        stopped_reason = "budget_exhausted"
        state = initial

        depth = 0
        while not self._budget.exhausted():
            try:
                score = self._score_fn(depth, state)
            except Exception:  # noqa: BLE001
                stopped_reason = "error"
                break
            self._history.append(score)
            if score > best_score:
                best_score = score
                best_depth = depth
                no_improve = 0
            else:
                no_improve += 1
            self._budget.record(depth=1)
            # estimar tokens (heuristica: 100 por iteracion)
            self._budget.record(tokens=100, depth=0)
            depth += 1
            if no_improve >= self._patience:
                stopped_reason = "early_stop_convergence"
                break
            if self._budget.exhausted():
                stopped_reason = "budget_exhausted"
                break
            state = score  # estado para siguiente iteracion

        if best_score == float("-inf"):
            best_score = 0.0
            stopped_reason = "no_iterations"

        return {
            "best_score": best_score,
            "best_depth": best_depth,
            "history": self._history,
            "stopped_reason": stopped_reason,
            "tokens_used": self._budget.tokens_used,
            "depth_used": self._budget.depth_used,
        }


__all__ = ["BoundedRecursion", "RecursionBudget"]
