"""Modelos de pools de tokens: ``TokenPool`` y ``TokenBudget``.

Extraido mecanicamente de ``token_budget.py`` (regla AGR < 500 lineas).
Sin cambios de logica ni de firmas: las clases conservan la misma API
publica y privada del modulo plano original.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from .constants import (
    ALL_POOLS,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    DEFAULT_AGENT_BUDGET,
    DEFAULT_POOL_ALLOCATION,
    MIN_RESERVE_TOKENS,
    POOL_CONVERSATION,
    POOL_RAG,
    POOL_SKILL,
    POOL_SYSTEM,
    POOL_TOOL_OUTPUT,
    POOL_USER,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
)

logger = logging.getLogger("harness.memory_rag.token_budget")


@dataclass
class TokenPool:
    """A single token pool with usage tracking."""
    name: str
    allocated: int = 0          # Tokens allocated to this pool
    used: int = 0               # Tokens used so far
    reserved: int = 0           # Reserved but not yet used
    priority: int = PRIORITY_NORMAL

    @property
    def remaining(self) -> int:
        return max(0, self.allocated - self.used - self.reserved)

    @property
    def usage_pct(self) -> float:
        if self.allocated == 0:
            return 0.0
        return self.used / self.allocated

    def can_allocate(self, tokens: int) -> bool:
        return self.remaining >= tokens

    def allocate(self, tokens: int) -> int:
        """Allocate tokens from this pool. Returns actual tokens allocated."""
        available = self.remaining
        actual = min(tokens, available)
        self.reserved += actual
        return actual

    def commit(self, tokens: int) -> None:
        """Commit reserved tokens as used."""
        actual = min(tokens, self.reserved)
        self.used += actual
        self.reserved -= actual

    def release(self, tokens: int) -> None:
        """Release reserved tokens back to pool."""
        actual = min(tokens, self.reserved)
        self.reserved -= actual

    def reset(self) -> None:
        self.used = 0
        self.reserved = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "allocated": self.allocated,
            "used": self.used,
            "reserved": self.reserved,
            "remaining": self.remaining,
            "usage_pct": round(self.usage_pct * 100, 1),
            "priority": self.priority,
        }


@dataclass
class TokenBudget:
    """
    Token budget for a single agent or session.

    Features:
      - Priority-weighted allocation across token pools
      - Confidence-gated spending (stop spending when confidence is high)
      - Minimum reserve to prevent starvation
      - Dynamic redistribution from low-priority to high-priority pools
    """
    agent_id: str
    total_budget: int = DEFAULT_AGENT_BUDGET
    priority: int = PRIORITY_NORMAL
    pool_allocation: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_POOL_ALLOCATION))
    confidence: float = 0.0
    min_reserve: int = MIN_RESERVE_TOKENS
    pools: dict[str, TokenPool] = field(default_factory=dict)
    parent_session: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _agent_failures: dict[str, int] = field(default_factory=dict)
    max_failures: int = 3
    disabled: bool = False

    def __post_init__(self) -> None:
        # Initialize pools with allocation
        for pool_name in ALL_POOLS:
            alloc_pct = self.pool_allocation.get(pool_name, 0.0)
            allocated = int(self.total_budget * alloc_pct)
            priority = self._pool_priority(pool_name)
            self.pools[pool_name] = TokenPool(
                name=pool_name,
                allocated=allocated,
                priority=priority,
            )

    @staticmethod
    def _pool_priority(pool_name: str) -> int:
        """Priority of each pool. System and user are most critical."""
        priorities = {
            POOL_SYSTEM: PRIORITY_CRITICAL,
            POOL_USER: PRIORITY_HIGH,
            POOL_RAG: PRIORITY_NORMAL,
            POOL_SKILL: PRIORITY_NORMAL,
            POOL_TOOL_OUTPUT: PRIORITY_LOW,
            POOL_CONVERSATION: PRIORITY_LOW,
        }
        return priorities.get(pool_name, PRIORITY_NORMAL)

    @property
    def total_used(self) -> int:
        return sum(p.used for p in self.pools.values())

    @property
    def total_remaining(self) -> int:
        return max(0, self.total_budget - self.total_used)

    @property
    def usage_pct(self) -> float:
        if self.total_budget == 0:
            return 0.0
        return self.total_used / self.total_budget

    @property
    def can_spend(self) -> bool:
        """
        Whether this agent can continue spending.
        Blocked if:
          - Pool disabled (exceeded max failures)
          - Confidence is high (>90%) → no more spending needed
          - Budget is exhausted with no reserve
        """
        if self.disabled:
            return False
        if self.confidence >= CONFIDENCE_HIGH:
            return False
        return not self.total_remaining <= self.min_reserve

    def set_confidence(self, confidence: float) -> None:
        """Set agent confidence level. Affects spending eligibility."""
        with self._lock:
            self.confidence = max(0.0, min(1.0, confidence))

    def record_failure(self, agent_id: str, tokens_used: int) -> None:
        """
        Registrar un fallo del agente y reducir presupuesto disponible.

        Si el agente excede max_failures, se desactiva el pool.

        Args:
            agent_id: Identificador del agente que falló.
            tokens_used: Cantidad de tokens consumidos en el intento fallido.
        """
        with self._lock:
            self._agent_failures[agent_id] = self._agent_failures.get(agent_id, 0) + 1
            # Penalizar: reducir presupuesto en 50% de tokens usados
            penalty = int(tokens_used * 0.5)
            self.total_budget = max(0, self.total_budget - penalty)
            # Ajustar pools proporcionalmente
            if self.total_budget > 0:
                for pool in self.pools.values():
                    pool.allocated = int(self.total_budget * self.pool_allocation.get(pool.name, 0.0))
            # Desactivar si excede max_failures
            if self._agent_failures[agent_id] >= self.max_failures:
                self.disabled = True
                logger.warning(
                    "TokenBudget[%s]: desactivado por exceder %d fallos (agente=%s)",
                    self.agent_id, self.max_failures, agent_id,
                )

    def request(self, pool_name: str, tokens: int) -> int:
        """
        Request tokens from a specific pool.
        Returns actual tokens granted (may be less than requested).
        """
        with self._lock:
            # Confidence gate
            if self.confidence >= CONFIDENCE_HIGH and pool_name not in (POOL_SYSTEM, POOL_USER):
                logger.debug(
                    "TokenBudget[%s]: blocked by confidence gate (%.2f >= %.2f)",
                    self.agent_id, self.confidence, CONFIDENCE_HIGH,
                )
                return 0

            # Reduce allocation if medium confidence
            if self.confidence >= CONFIDENCE_MEDIUM:
                tokens = int(tokens * 0.5)

            pool = self.pools.get(pool_name)
            if not pool:
                logger.warning("TokenBudget[%s]: unknown pool '%s'", self.agent_id, pool_name)
                return 0

            allocated = pool.allocate(tokens)

            # If pool is exhausted, try redistributing from lower-priority pools
            if allocated < tokens:
                deficit = tokens - allocated
                redistributed = self._redistribute(pool_name, deficit)
                allocated += redistributed

            logger.debug(
                "TokenBudget[%s]: pool=%s requested=%d granted=%d remaining=%d",
                self.agent_id, pool_name, tokens, allocated, pool.remaining,
            )
            return allocated

    def commit(self, pool_name: str, tokens: int) -> None:
        """Commit previously reserved tokens as used."""
        with self._lock:
            pool = self.pools.get(pool_name)
            if pool:
                pool.commit(tokens)

    def release(self, pool_name: str, tokens: int) -> None:
        """Release reserved tokens back (e.g. if not needed)."""
        with self._lock:
            pool = self.pools.get(pool_name)
            if pool:
                pool.release(tokens)

    def snapshot(self) -> dict[str, Any]:
        """Return budget snapshot for monitoring/reporting."""
        with self._lock:
            return {
                "agent_id": self.agent_id,
                "total_budget": self.total_budget,
                "total_used": self.total_used,
                "total_remaining": self.total_remaining,
                "usage_pct": round(self.usage_pct * 100, 1),
                "priority": self.priority,
                "confidence": round(self.confidence, 3),
                "can_spend": self.can_spend,
                "pools": {k: v.to_dict() for k, v in self.pools.items()},
                "parent_session": self.parent_session,
            }

    def _redistribute(self, needy_pool: str, deficit: int) -> int:
        """
        Redistribute tokens from lower-priority pools to the needy pool.
        Tokens only flow uphill (from lower priority to higher priority).
        """
        needy_priority = self._pool_priority(needy_pool)
        total_redistributed = 0

        # Sort pools by priority (ascending) so we take from lowest first
        sorted_pools = sorted(
            self.pools.items(),
            key=lambda x: x[1].priority,
        )

        for pool_name, pool in sorted_pools:
            if pool_name == needy_pool:
                continue
            # Only take from lower-priority pools
            if pool.priority >= needy_priority:
                continue
            # Don't drain below min_reserve
            available = max(0, pool.remaining - self.min_reserve)
            if available <= 0:
                continue

            take = min(available, deficit - total_redistributed)
            if take > 0:
                pool.used += take  # transfer to used (effectively consumed)
                total_redistributed += take
                logger.debug(
                    "TokenBudget[%s]: redistributed %d from '%s' to '%s'",
                    self.agent_id, take, pool_name, needy_pool,
                )

            if total_redistributed >= deficit:
                break

        return total_redistributed
