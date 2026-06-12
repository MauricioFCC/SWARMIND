"""
Orquestador multi-agente: task management, delegacion, bus de mensajes y sandbox loop.

Exporta las clases principales del modulo de orquestacion:
- TaskManager: Gestion de tareas con LanceDB + SQLite fallback
- DelegationEngine: Enrutamiento de mensajes a agentes por @rol o intent matching
- AgentBus: Bus de mensajes asincrono entre agentes (Slack para Agentes)
- SandboxLoop: Bucle autonomo de calidad con circuit breaker
"""
from harness.orchestrator.task_manager import TaskManager
from harness.orchestrator.delegation_engine import DelegationEngine
from harness.orchestrator.agent_bus import AgentBus, AgentBusError, InvalidMessageError
from harness.orchestrator.sandbox_loop import SandboxLoop

__all__ = [
    "TaskManager",
    "DelegationEngine",
    "AgentBus",
    "AgentBusError",
    "InvalidMessageError",
    "SandboxLoop",
]
