"""Budget manager a nivel de sesion: ``BudgetManager`` y singleton.

Extraido mecanicamente de ``token_budget.py`` (regla AGR < 500 lineas).
Contiene el gestor multi-agente de budgets, el singleton perezoso
``get_token_budget_manager`` y su variable global.

Nota: ``register_agent`` resuelve ``get_token_budget_manager`` a traves del
paquete (``_token_budget.get_token_budget_manager()``) para replicar el
global lookup del modulo plano original: parches de tests como
``monkeypatch.setattr(tb, "get_token_budget_manager", lambda: manager)``
siguen afectando a ``register_agent`` (mismo patron que lance_vector_store).
"""
from __future__ import annotations

import logging
import threading
from typing import Any

# Import del paquete para resolver get_token_budget_manager en runtime
# (ver nota del docstring de modulo).
import harness.memory_rag.token_budget as _token_budget

from .constants import (
    DEFAULT_AGENT_BUDGET,
    DEFAULT_SESSION_BUDGET,
    MIN_RESERVE_TOKENS,
    PRIORITY_NORMAL,
)
from .pools import TokenBudget

logger = logging.getLogger("harness.memory_rag.token_budget")


# ---------------------------------------------------------------------------
# Budget Manager (session-level)
# ---------------------------------------------------------------------------

_token_budget_manager_instance: Any = None


def get_token_budget_manager() -> Any:
    """Retorna el TokenBudgetManager global (singleton perezoso).

    WHAT: Crea o reutiliza la instancia unica del manager de budgets que
    carga el SSOT ``.opencode/config/token_budgets.yaml``.
    WHY: Evitar reparsear el YAML en cada registro de agente; la
    configuracion de budgets es global y de solo lectura.
    WHERE: ``BudgetManager.register_agent`` — resolucion de budget por rol
    (ADR-0040 H6).

    Returns:
        Instancia unica de ``TokenBudgetManager``.
    """
    global _token_budget_manager_instance
    if _token_budget_manager_instance is None:
        # Import local: evita ciclo de importacion (el manager importa
        # constantes de este modulo en tiempo de carga).
        from harness.memory_rag.token_budget_manager import TokenBudgetManager

        _token_budget_manager_instance = TokenBudgetManager()
    return _token_budget_manager_instance


class BudgetManager:
    """
    Manages token budgets across all agents in a session.

    Features:
      - Per-agent budget creation with priority
      - Cross-agent redistribution (idle budget flows to busy agents)
      - Session-level budget cap
      - Monitoring and reporting
    """

    def __init__(
        self,
        session_budget: int = DEFAULT_SESSION_BUDGET,
        default_agent_budget: int = DEFAULT_AGENT_BUDGET,
        min_reserve: int = MIN_RESERVE_TOKENS,
    ) -> None:
        self._session_budget = session_budget
        self._default_agent_budget = default_agent_budget
        self._min_reserve = min_reserve
        self._agent_budgets: dict[str, TokenBudget] = {}
        self._lock = threading.Lock()

        logger.info(
            "BudgetManager initialized (session=%d, agent=%d, reserve=%d)",
            session_budget, default_agent_budget, min_reserve,
        )

    def register_agent(
        self,
        agent_id: str,
        budget: int | None = None,
        priority: int = PRIORITY_NORMAL,
        session_id: str | None = None,
    ) -> TokenBudget:
        """Register an agent with its token budget."""
        with self._lock:
            if agent_id in self._agent_budgets:
                logger.debug("BudgetManager: agent '%s' already registered", agent_id)
                return self._agent_budgets[agent_id]

            # Presupuesto por rol desde el SSOT token_budgets.yaml (ADR-0040 H6):
            # si el rol esta declarado, se aplica su budget (ej. guardian 2048);
            # si el YAML no existe o el rol no esta, se usa el default historico.
            if budget:
                total_budget = budget
            else:
                role_budget = _token_budget.get_token_budget_manager().get_role_budget(agent_id)
                total_budget = role_budget if role_budget is not None else self._default_agent_budget

            agent_budget = TokenBudget(
                agent_id=agent_id,
                total_budget=total_budget,
                priority=priority,
                min_reserve=self._min_reserve,
                parent_session=session_id,
            )
            self._agent_budgets[agent_id] = agent_budget
            logger.info(
                "BudgetManager: registered '%s' (budget=%d, priority=%d)",
                agent_id, agent_budget.total_budget, priority,
            )
            return agent_budget

    def get_budget(self, agent_id: str) -> TokenBudget | None:
        """Get an agent's budget."""
        return self._agent_budgets.get(agent_id)

    def get_or_create(
        self,
        agent_id: str,
        budget: int | None = None,
        priority: int = PRIORITY_NORMAL,
    ) -> TokenBudget:
        """Get existing budget or create one."""
        existing = self.get_budget(agent_id)
        if existing:
            return existing
        return self.register_agent(agent_id, budget, priority)

    def redistribute_idle(self) -> dict[str, int]:
        """
        Redistribute unused budget from idle/completed agents to active ones.
        Idle = confidence >= HIGH or can_spend == False.
        Returns {agent_id: tokens_received}.
        """
        with self._lock:
            # Find donors (idle agents with remaining budget)
            donors: list[tuple[str, int, int]] = []  # (agent_id, remaining, priority)
            recipients: list[tuple[str, TokenBudget, int]] = []  # (agent_id, budget, priority)

            for agent_id, budget in self._agent_budgets.items():
                if not budget.can_spend and budget.total_remaining > self._min_reserve:
                    donors.append((agent_id, budget.total_remaining - self._min_reserve, budget.priority))
                elif budget.can_spend:
                    recipients.append((agent_id, budget, budget.priority))

            if not donors or not recipients:
                return {}

            # Sort donors by priority ascending (give from least important)
            donors.sort(key=lambda x: x[2])
            # Sort recipients by priority descending (give to most important)
            recipients.sort(key=lambda x: x[2], reverse=True)

            total_redistributed: dict[str, int] = {}
            for donor_id, donor_remaining, _ in donors:
                if donor_remaining <= 0:
                    continue
                for recipient_id, recipient_budget, _ in recipients:
                    if donor_remaining <= 0:
                        break
                    # Give to recipient
                    give = min(donor_remaining, self._default_agent_budget // 4)
                    recipient_budget.total_budget += give
                    # Credit to general pool
                    for pool in recipient_budget.pools.values():
                        pool.allocated += int(give * pool.allocated / max(recipient_budget.total_budget - give, 1))

                    total_redistributed[recipient_id] = total_redistributed.get(recipient_id, 0) + give
                    donor_remaining -= give

                    logger.debug(
                        "BudgetManager: redistributed %d from '%s' to '%s'",
                        give, donor_id, recipient_id,
                    )

            return total_redistributed

    def session_snapshot(self, session_id: str) -> dict[str, Any]:
        """Get budget snapshot for all agents in a session."""
        agents = {}
        for agent_id, budget in self._agent_budgets.items():
            if budget.parent_session == session_id:
                agents[agent_id] = budget.snapshot()

        total_budget = sum(a["total_budget"] for a in agents.values())
        total_used = sum(a["total_used"] for a in agents.values())

        return {
            "session_id": session_id,
            "total_budget_allocated": total_budget,
            "total_used": total_used,
            "total_remaining": total_budget - total_used,
            "usage_pct": round(total_used / max(total_budget, 1) * 100, 1),
            "agents": agents,
        }

    def reset_session(self, session_id: str) -> int:
        """Reset all budgets for a session. Returns count of agents reset."""
        with self._lock:
            to_remove = [
                aid for aid, b in self._agent_budgets.items()
                if b.parent_session == session_id
            ]
            for aid in to_remove:
                del self._agent_budgets[aid]
            return len(to_remove)

    def get_stats(self) -> dict[str, Any]:
        """Get global budget manager statistics."""
        return {
            "session_budget": self._session_budget,
            "default_agent_budget": self._default_agent_budget,
            "min_reserve": self._min_reserve,
            "agents_registered": len(self._agent_budgets),
            "total_budget_allocated": sum(b.total_budget for b in self._agent_budgets.values()),
            "total_used": sum(b.total_used for b in self._agent_budgets.values()),
        }
