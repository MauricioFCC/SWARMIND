"""Agent Message Bus — "Slack para Agentes".

Antes: harness/orchestrator/agent_bus.py (715 lineas).
Ahora: paquete ``harness/orchestrator/agent_bus/``:

- ``constants.py``: constantes de coleccion y validacion.
- ``exceptions.py``: AgentBusError, InvalidMessageError.
- ``core.py``: clase ``AgentBus`` (estado + payload + helpers).
- ``messaging.py``: mixin ``_MessagingMixin`` (post/batch/async).
- ``reading.py``: mixin ``_ReadingMixin`` (poll/thread/history).
- ``status.py``: mixin ``_StatusMixin`` (estados + circuit breaker).
- ``utils.py``: mixin ``_UtilsMixin`` (listados + validaciones).
- ``async_bus.py``: clase ``AsyncAgentBus`` (asyncio.Queue PaCoRe).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos (y las
constantes internas usadas por tests) del modulo original para
mantener backward-compat:

    from harness.orchestrator.agent_bus import AgentBus

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from .async_bus import AsyncAgentBus
from .constants import (
    _COLLECTION,
    _EMBEDDING_DIM,
    _VALID_MESSAGE_TYPES,
    _VALID_STATUSES,
)
from .core import AgentBus
from .exceptions import AgentBusError, InvalidMessageError

__all__ = [
    "_COLLECTION",
    "_EMBEDDING_DIM",
    "_VALID_MESSAGE_TYPES",
    "_VALID_STATUSES",
    "AgentBus",
    "AgentBusError",
    "AsyncAgentBus",
    "InvalidMessageError",
]
