"""federation — Federación de agentes entre proyectos (ADR-0058).

Implementa los conceptos de A2A v1.0 (Linux Foundation) con transporte
local: Agent Cards para descubrimiento, task lifecycle gobernado y
activación del harness del proyecto destino.

Módulos:
- agent_card: identidad y descubrimiento (.opencode/.well-known/agent-card.json)
- task_protocol: estados de tarea + store idempotente
- federation_bus: envío gobernado deny-by-default + audit trail
"""
from harness.federation.agent_card import (
    AGENT_CARD_FILENAME,
    AgentCard,
    AgentSkill,
    discover_cards,
    load_agent_card,
    write_agent_card,
)
from harness.federation.federation_bus import FederationBus, GovernancePolicy
from harness.federation.task_protocol import (
    FederatedTask,
    TaskState,
    TaskStore,
)

__all__ = [
    "AGENT_CARD_FILENAME",
    "AgentCard",
    "AgentSkill",
    "FederatedTask",
    "FederationBus",
    "GovernancePolicy",
    "TaskState",
    "TaskStore",
    "discover_cards",
    "load_agent_card",
    "write_agent_card",
]
