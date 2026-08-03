"""Tests TDD (spec-first) para TokenBudgetManager.

Contrato (spec):
- Cada sesión tiene un budget (default 4096).
- track_usage(session_id, tokens) registra uso, respeta budget, devuelve
  métricas de la sesión.
- get_remaining(session_id) devuelve budget - usado (>= 0).
- get_usage(session_id) devuelve dict o None si la sesión no existe.
- reset_session(session_id) reinicia a budget inicial.
- set_budget(session_id, new_budget) actualiza el budget.
- get_all_sessions() devuelve todas las sesiones.
- get_stats() devuelve métricas globales.

Invariantes (PBT):
- Para cualquier sesión y uso válido: remaining = budget - used >= 0.
- track_usage devuelve la misma sesión en todas las llamadas.
"""
from __future__ import annotations

import pytest

from harness.memory_rag.token_budget_manager import TokenBudgetManager


@pytest.fixture
def manager() -> TokenBudgetManager:
    """Crea un manager limpio (estado en memoria)."""
    return TokenBudgetManager(default_budget=4000, max_sessions=100)


class TestTokenBudgetManagerContract:
    """Contrato principal del manager de presupuestos."""

    def test_get_remaining_unknown_session_returns_zero(self, manager: TokenBudgetManager) -> None:
        """Spec: get_remaining de sesión inexistente devuelve 0."""
        assert manager.get_remaining("nueva") == 0

    def test_track_usage_creates_session_with_budget(self, manager: TokenBudgetManager) -> None:
        """Spec: track_usage crea la sesión con el budget por defecto."""
        result = manager.track_usage("s1", 1000)
        assert result is not None
        assert result.get("session_id") == "s1"
        assert result.get("used", 0) == 1000
        assert result.get("remaining", 0) == 3000

    def test_get_remaining_reflects_usage(self, manager: TokenBudgetManager) -> None:
        """Spec: get_remaining devuelve budget menos usado."""
        manager.track_usage("s1", 2000)
        assert manager.get_remaining("s1") == 2000

    def test_get_usage_unknown_session_returns_none(self, manager: TokenBudgetManager) -> None:
        """Spec: get_usage de sesión inexistente devuelve None."""
        assert manager.get_usage("fantasma") is None

    def test_get_usage_known_session(self, manager: TokenBudgetManager) -> None:
        """Spec: get_usage de sesión conocida devuelve dict."""
        manager.track_usage("s1", 500)
        usage = manager.get_usage("s1")
        assert usage is not None
        assert usage["session_id"] == "s1"
        assert usage["used"] == 500

    def test_reset_session(self, manager: TokenBudgetManager) -> None:
        """Spec: reset_session elimina la sesión (get_remaining vuelve a 0)."""
        manager.track_usage("s1", 3000)
        assert manager.reset_session("s1") is True
        assert manager.get_remaining("s1") == 0

    def test_reset_unknown_session_returns_false(self, manager: TokenBudgetManager) -> None:
        """Spec: reset_session de sesión inexistente devuelve False."""
        assert manager.reset_session("fantasma") is False

    def test_set_budget(self, manager: TokenBudgetManager) -> None:
        """Spec: set_budget actualiza el budget de la sesión."""
        manager.track_usage("s1", 100)
        assert manager.set_budget("s1", 8192) is True
        assert manager.get_remaining("s1") == 8092

    def test_set_budget_unknown_returns_false(self, manager: TokenBudgetManager) -> None:
        """Spec: set_budget de sesión inexistente devuelve False."""
        assert manager.set_budget("fantasma", 8192) is False

    def test_get_all_sessions(self, manager: TokenBudgetManager) -> None:
        """Spec: get_all_sessions devuelve todas las sesiones registradas."""
        manager.track_usage("s1", 100)
        manager.track_usage("s2", 200)
        sessions = manager.get_all_sessions()
        assert set(sessions.keys()) == {"s1", "s2"}

    def test_get_stats(self, manager: TokenBudgetManager) -> None:
        """Spec: get_stats devuelve métricas globales."""
        manager.track_usage("s1", 1000)
        stats = manager.get_stats()
        assert "active_sessions" in stats
        assert stats["active_sessions"] == 1
        assert stats["total_used"] == 1000


class TestTokenBudgetManagerInvariants:
    """Invariantes del contrato (spec-first)."""

    def test_remaining_never_negative(self, manager: TokenBudgetManager) -> None:
        """Invariante: remaining nunca es negativo tras uso excesivo."""
        manager.track_usage("s1", 9000)  # supera budget 4000
        remaining = manager.get_remaining("s1")
        assert remaining >= 0

    def test_track_usage_idempotent_session(self, manager: TokenBudgetManager) -> None:
        """Invariante: la misma sesión se acumula en la misma entrada."""
        manager.track_usage("s1", 100)
        manager.track_usage("s1", 150)
        usage = manager.get_usage("s1")
        assert usage is not None
        assert usage["used"] == 250

    def test_budget_respected(self, manager: TokenBudgetManager) -> None:
        """Invariante: nunca se excede el budget en remaining reportado."""
        manager.track_usage("s1", 5000)
        manager.track_usage("s1", 5000)
        assert manager.get_remaining("s1") == 0  # saturado, no negativo
