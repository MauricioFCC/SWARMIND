"""Proposer interface (Harness2-inspired)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class ProposerError(Exception):
    """Raised when a proposal fails."""

    def __init__(self, message: str, *, attempts: int = 0, cost_usd: float = 0.0) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.cost_usd = cost_usd


@dataclass
class Proposer:
    """Wraps a callable that proposes harness edits.

    The callable signature: (mission: str, root: Path, label: str) -> dict
    returning a new harness tree (as dict). May raise.
    """

    call_fn: Callable[[str, Any, str], Any]
    max_attempts: int = 2

    def call(self, mission: str, root: Any, label: str, *, max_attempts: int | None = None) -> Any:
        attempts = max_attempts or self.max_attempts
        last_exc: Exception | None = None
        for i in range(1, attempts + 1):
            try:
                return self.call_fn(mission, root, label)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        raise ProposerError(str(last_exc), attempts=attempts)
