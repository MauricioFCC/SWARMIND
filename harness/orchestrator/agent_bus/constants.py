"""Constantes del AgentBus (extraidas tal cual del modulo original)."""

from __future__ import annotations

_COLLECTION = "agent_workspace_logs"
_EMBEDDING_DIM = 384

_VALID_MESSAGE_TYPES = frozenset({
    "request", "response", "error", "notification", "escalation",
})
_VALID_STATUSES = frozenset({"sent", "delivered", "acknowledged"})
