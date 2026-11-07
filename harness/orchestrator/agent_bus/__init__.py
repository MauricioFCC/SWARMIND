"""Agent Message Bus — "Slack para Agentes".

Estructura del paquete ``harness/orchestrator/agent_bus/``:

- ``constants.py``: constantes de coleccion y validacion.
- ``errors.py``: ``AgentBusError`` / ``InvalidMessageError`` (sin dependencias).
- ``core.py``: clase ``AgentBus`` (estado + payload + helpers).
- ``messaging.py``: mixin ``_MessagingMixin`` (post/batch/async).
- ``reading.py``: mixin ``_ReadingMixin`` (poll/thread/history).
- ``async_bus.py``: clase ``AsyncAgentBus`` (asyncio.Queue PaCoRe).
- ``kernel_bus.py``: ``KernelBus`` determinista sobre ``harness.kernel``
  (single-loop FIFO + event log replayable).

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
from .core import AgentBus, AgentBusError, InvalidMessageError
from .kernel_bus import KernelBus, KernelBusError

__all__ = [
    "_COLLECTION",
    "_EMBEDDING_DIM",
    "_VALID_MESSAGE_TYPES",
    "_VALID_STATUSES",
    "AgentBus",
    "AgentBusError",
    "AsyncAgentBus",
    "InvalidMessageError",
    "KernelBus",
    "KernelBusError",
]
